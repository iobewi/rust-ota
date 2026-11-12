"""Qualified stable OTA reboot: independent BOOT/OTM1 persistence evidence.

Requires an operator-approved plan with exact hash. A reset is a physical
side effect; no implicit reset, firmware write, retry or recovery.
Run separately from upload/activation. The DUT must already be Stable.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from boot_metadata import SECTOR, assert_no_unconfirmed_new_selection, decode_otadata
from diagnostic import validate_diagnostic
from ota_http import OtaHttp
from ota_meta import decode_ota_meta
from test_activation import wait_diagnostic

pytestmark = pytest.mark.bench


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def stable_reset_plan():
    if os.getenv("OTA_APPROVED_STABLE_RESET") != "yes":
        pytest.skip("Stable reset needs a separate operator approval")
    path = os.getenv("OTA_STABLE_RESET_PLAN")
    digest = os.getenv("OTA_STABLE_RESET_PLAN_SHA256")
    if not path or not digest or _sha(path) != digest:
        pytest.fail("Missing/mismatched approved stable reset plan; no bench access")
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "schema", "scope", "device", "mcu", "flash_size", "table_offset",
        "otadata_offset", "ota_meta_offset", "expected_build_id", "expected_slot",
    }
    assert isinstance(plan, dict) and set(plan) == expected
    assert plan["schema"] == 1 and plan["scope"] == "ota.stable-reset-persistence"
    assert plan["mcu"] in ("esp32c3", "esp32s3")
    assert type(plan["flash_size"]) is int and plan["flash_size"] > 0
    assert type(plan["expected_slot"]) is int and plan["expected_slot"] in (0, 1)
    assert isinstance(plan["expected_build_id"], str) and plan["expected_build_id"]
    assert os.getenv("BENCH_DEVICE", "esp32-local") == plan["device"]
    for name in ("table_offset", "otadata_offset", "ota_meta_offset"):
        offset = plan[name]
        assert type(offset) is int and offset >= 0 and offset % SECTOR == 0
        assert offset < plan["flash_size"]
    for name in ("otadata_offset", "ota_meta_offset"):
        assert plan[name] + 2 * SECTOR <= plan["flash_size"]
    assert plan["otadata_offset"] != plan["ota_meta_offset"]
    return plan


def _flash_state(board, plan):
    boot = board.read_flash(address=plan["otadata_offset"], size=2 * SECTOR)
    meta = board.read_flash(address=plan["ota_meta_offset"], size=2 * SECTOR)
    records = assert_no_unconfirmed_new_selection(boot)
    store = decode_ota_meta(meta)
    assert store["kind"] == "Payload" and store["metadata"]["stage"] == "None"
    assert any(r["kind"] == "Ok" and r["state"] == "Valid"
               and r["slot"] == plan["expected_slot"] for r in records)
    return boot, meta, store


def test_stable_reset_preserves_confirmed_ota_state(stable_reset_plan, ota_campaign):
    plan = stable_reset_plan
    token = os.getenv("IOBEWI_OTA_TOKEN")
    origin = os.getenv("OTA_HTTPS_ORIGIN")
    ca = os.getenv("OTA_CA_FILE")
    if not all((token, origin, ca)):
        pytest.fail("Missing private verified HTTPS settings")
    app = OtaHttp(origin, ca, token, timeout=30)
    board = ota_campaign.reserve(ttl=1800)
    identity = board.identify()
    assert identity["chip"] == plan["mcu"]
    assert identity["flash_size"] == plan["flash_size"]
    table = {p["label"]: p for p in board.partitions(address=plan["table_offset"])}
    for name, offset in (("otadata", "otadata_offset"), ("ota_meta", "ota_meta_offset")):
        assert name in table
        assert table[name]["address"] == plan[offset]
        assert table[name]["size"] == 2 * SECTOR

    before_runtime = wait_diagnostic(
        app, plan["expected_build_id"], plan["mcu"], identity["mac"]
    )
    assert before_runtime["running_slot"] == plan["expected_slot"]
    boot_before, meta_before, store_before = _flash_state(board, plan)
    ota_campaign.write("stable-reset-before.json", {
        "boot_sha256": hashlib.sha256(boot_before).hexdigest(),
        "ota_meta_sha256": hashlib.sha256(meta_before).hexdigest(),
        "runtime_build_id": before_runtime["build_id"],
        "slot": before_runtime["running_slot"],
        "otm1_sequence": store_before["sequence"],
    })

    # This operation may change USB generation and invalidate the reservation.
    # Never submit reset a second time after an uncertain result.
    try:
        board.command("reset", {}, timeout=30)
    finally:
        board.close()

    # Poll GET only; no implicit reset or firmware mutation.
    after_runtime = wait_diagnostic(
        app, plan["expected_build_id"], plan["mcu"], identity["mac"], timeout=90
    )
    assert after_runtime["running_slot"] == plan["expected_slot"]
    board_after = ota_campaign.reserve(ttl=1800)
    assert board_after.identify()["chip"] == plan["mcu"]
    boot_after, meta_after, store_after = _flash_state(board_after, plan)
    assert boot_after == boot_before, "BOOT metadata changed after Stable reset"
    assert meta_after == meta_before, "OTM1 metadata changed after Stable reset"
    ota_campaign.write("stable-reset-after.json", {
        "boot_sha256": hashlib.sha256(boot_after).hexdigest(),
        "ota_meta_sha256": hashlib.sha256(meta_after).hexdigest(),
        "runtime_build_id": after_runtime["build_id"],
        "slot": after_runtime["running_slot"],
        "otm1_sequence": store_after["sequence"],
        "persisted_across_reset": True,
        "authenticity_independently_verified": False,
    })
