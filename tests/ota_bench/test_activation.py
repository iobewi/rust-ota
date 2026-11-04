"""Gated A->B activation, confirmation, and durable readback.

This intentionally does NOT perform the staging POST. Requires a separate,
already staged candidate and explicit approval for metadata-changing activate.
No retry of activation, no unattended power interruption, no automatic rollback.
"""
import hashlib
import json
import os
from pathlib import Path
import time

import pytest

from boot_metadata import SECTOR, assert_no_unconfirmed_new_selection
from boot_transitions import require_confirmed_transition
from diagnostic import validate_diagnostic
from ota_http import OtaHttp, OtaTransportUncertain
from ota_meta import decode_ota_meta

pytestmark = pytest.mark.bench


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture
def approved_activation():
    if os.getenv("OTA_APPROVED_ACTIVATION") != "yes":
        pytest.skip("Activation requires separate explicit operator approval")
    path, expected = os.getenv("OTA_ACTIVATION_PLAN"), os.getenv("OTA_ACTIVATION_PLAN_SHA256")
    if not path or not expected or digest(path) != expected:
        pytest.fail("Missing or changed activation plan; no hardware access")
    plan = json.loads(Path(path).read_text())
    required = {
        "schema", "scope", "device", "mcu", "flash_size", "table_offset",
        "pre_activation_flash", "pre_activation_sha256", "baseline_build_id",
        "candidate_build_id", "candidate_image", "candidate_sha256",
        "candidate_manifest", "deployment_id", "otadata_offset", "ota_meta_offset",
        "slot_0", "slot_1", "preserved_regions",
    }
    assert required <= set(plan), "Incomplete approved activation plan"
    assert plan["schema"] == 1 and plan["scope"] == "ota.activate-confirm-readback"
    assert plan["mcu"] == "esp32c3" and plan["flash_size"] == 4 * 1024 * 1024
    assert os.environ.get("BENCH_DEVICE", "esp32-local") == plan["device"]
    assert plan["baseline_build_id"] != plan["candidate_build_id"]
    for name in ("pre_activation_flash", "candidate_image", "candidate_manifest"):
        assert os.path.isabs(plan[name]), f"Private path required: {name}"
    assert Path(plan["pre_activation_flash"]).stat().st_size == plan["flash_size"]
    for file, expected_hash in (
        ("pre_activation_flash", "pre_activation_sha256"),
        ("candidate_image", "candidate_sha256"),
    ):
        assert digest(plan[file]) == plan[expected_hash], f"Changed {file}"
    assert isinstance(plan["preserved_regions"], list)
    assert plan["preserved_regions"], "Explicit preserved regions required"
    for region in plan["preserved_regions"]:
        assert set(region) == {"label", "offset", "size"}
        assert type(region["offset"]) is int and type(region["size"]) is int
        assert 0 <= region["offset"] and 0 < region["size"]
        assert region["offset"] + region["size"] <= plan["flash_size"]
    assert type(plan["otadata_offset"]) is int
    assert plan["otadata_offset"] % SECTOR == 0
    assert 0 <= plan["otadata_offset"] <= plan["flash_size"] - 2 * SECTOR
    assert type(plan["ota_meta_offset"]) is int
    assert plan["ota_meta_offset"] % SECTOR == 0
    assert 0 <= plan["ota_meta_offset"] <= plan["flash_size"] - 2 * SECTOR
    return plan


def wait_diagnostic(client, expected_build, expected_mcu, *, timeout=90):
    """Safe bounded GET-only polling; never replays activation."""
    end = time.monotonic() + timeout
    last = "not reached"
    while time.monotonic() < end:
        try:
            status, body = client.diagnostic()
            if status == 200:
                result = json.loads(body)
                # During controlled reset the old A can still respond briefly.
                if result.get("build_id") == expected_build:
                    return validate_diagnostic(
                        body, expected_build=expected_build, expected_mcu=expected_mcu
                    )
                last = "other build observed"
            else:
                last = f"HTTP {status}"
        except OtaTransportUncertain as error:
            last = type(error).__name__
        time.sleep(1)
    raise AssertionError(f"Expected runtime not confirmed in time ({last})")


def test_activate_and_confirm_from_independently_staged_image(
    approved_activation, ota_campaign
):
    plan = approved_activation
    token = os.getenv("IOBEWI_OTA_TOKEN")
    origin = os.getenv("OTA_HTTPS_ORIGIN")
    ca = os.getenv("OTA_CA_FILE")
    if not all((token, origin, ca)):
        pytest.fail("Missing private HTTPS credentials/identity")
    app = OtaHttp(origin, ca, token, timeout=120)
    board = ota_campaign.reserve(ttl=3600)
    identity = board.identify()
    assert identity["chip"] == plan["mcu"]
    assert identity["flash_size"] == plan["flash_size"]
    table = {p["label"]: p for p in board.partitions(address=plan["table_offset"])}
    assert {"ota_0", "ota_1", "otadata", "ota_meta"} <= set(table)
    for index in (0, 1):
        slot = plan[f"slot_{index}"]
        assert set(slot) == {"offset", "size"}
        assert (table[f"ota_{index}"]["address"], table[f"ota_{index}"]["size"]) == (
            slot["offset"], slot["size"]
        )
    assert table["otadata"]["address"] == plan["otadata_offset"]
    assert table["otadata"]["size"] == 2 * SECTOR
    assert table["ota_meta"]["address"] == plan["ota_meta_offset"]
    assert table["ota_meta"]["size"] == 2 * SECTOR
    for region in plan["preserved_regions"]:
        p = table[region["label"]]
        assert (p["address"], p["size"]) == (region["offset"], region["size"])

    snapshot = board.read_flash(address=0, size=plan["flash_size"], timeout=600)
    assert hashlib.sha256(snapshot).hexdigest() == plan["pre_activation_sha256"], (
        "Post-stage flash differs from approved snapshot; activation forbidden"
    )
    meta_offset = plan["otadata_offset"]
    old_meta = snapshot[meta_offset:meta_offset + 2 * SECTOR]
    assert_no_unconfirmed_new_selection(old_meta)
    board.renew(ttl=3600)

    before = wait_diagnostic(app, plan["baseline_build_id"], plan["mcu"])
    old_slot = before["running_slot"]
    target_slot = 1 - old_slot
    part = plan[f"slot_{target_slot}"]
    image = Path(plan["candidate_image"])
    image_size = image.stat().st_size
    assert 0 < image_size <= part["size"] - SECTOR
    assert hashlib.sha256(
        snapshot[part["offset"]:part["offset"] + image_size]
    ).hexdigest() == plan["candidate_sha256"], (
        "Staged candidate flash bytes disagree with approved image"
    )
    old_store_raw = snapshot[
        plan["ota_meta_offset"]:plan["ota_meta_offset"] + 2 * SECTOR
    ]
    old_store = decode_ota_meta(old_store_raw)
    assert old_store["kind"] == "Payload", "Candidate not durably staged"
    staged = old_store["metadata"]
    assert staged["stage"] == "Written"
    assert staged["slot"] == f"ota_{target_slot}"
    assert staged["digest"] == "sha256:" + plan["candidate_sha256"]
    assert staged["deployment_id"] == plan["deployment_id"]
    assert staged["size"] == image_size

    manifest = Path(plan["candidate_manifest"]).read_text(encoding="ascii").strip()
    OtaHttp.validate_manifest(manifest)
    ota_campaign.write("activation-before.json", {
        "running_slot": old_slot,
        "baseline_build": before["build_id"],
        "candidate_slot": target_slot,
        "candidate_digest": plan["candidate_sha256"],
        "approved_snapshot_sha256": plan["pre_activation_sha256"],
    })

    # A software reboot can change USB Serial/JTAG generation. Do not hold an
    # old bench reservation or attempt to use its stale Board after activation.
    board.close()

    # This POST changes otadata and reboots. Explicitly separately approved.
    # A lost response is indeterminate: never replay.
    status, body = app.activate(plan["deployment_id"], manifest=manifest)
    assert (status, body) == (200, b"activating"), (
        f"Activation not acknowledged: HTTP {status}"
    )

    after = wait_diagnostic(app, plan["candidate_build_id"], plan["mcu"])
    assert after["running_slot"] == target_slot, "Candidate did not become running image"
    # A newly created reservation must bind the current epoch and generation.
    board_after = ota_campaign.reserve(ttl=3600)
    assert board_after.identify()["chip"] == plan["mcu"]
    new_meta = board_after.read_flash(
        address=meta_offset, size=2 * SECTOR, timeout=600
    )
    transition = require_confirmed_transition(
        old_meta, new_meta, from_slot=old_slot, to_slot=target_slot
    )
    # Verify the OTA transaction was durably promoted and the staged intent
    # cleared; BOOT v2 Valid alone does not prove OTM1 finalization.
    new_store_raw = board_after.read_flash(
        address=plan["ota_meta_offset"], size=2 * SECTOR, timeout=600
    )
    new_store = decode_ota_meta(new_store_raw)
    assert new_store["kind"] == "Payload", "OTM1 store unavailable after confirmation"
    active = new_store["metadata"]
    assert active["stage"] == "None", "Staged activation not durably finalized"
    assert active["active_digest"] == "sha256:" + plan["candidate_sha256"]
    assert active["active_deployment_id"] == plan["deployment_id"]
    preserved = []
    for region in plan["preserved_regions"]:
        address, size = region["offset"], region["size"]
        current = board_after.read_flash(address=address, size=size, timeout=600)
        expected_digest = hashlib.sha256(snapshot[address:address + size]).hexdigest()
        assert hashlib.sha256(current).hexdigest() == expected_digest, (
            f"Unexpected change in preserved region: {region['label']}"
        )
        preserved.append({"label": region["label"], "sha256": expected_digest})

    ota_campaign.write("activation-after.json", {
        "candidate_build": after["build_id"],
        "running_slot": after["running_slot"],
        "boot_transition": transition,
        "preserved_regions": preserved,
        "boot_metadata_readback_sha256": hashlib.sha256(new_meta).hexdigest(),
        "otm1_independent_decode": True,
        "otm1_frame_copy": new_store["copy"],
        "otm1_frame_sequence": new_store["sequence"],
        "otm1_store_sha256": hashlib.sha256(new_store_raw).hexdigest(),
        "image_authentication_independently_verified": False,
    })
