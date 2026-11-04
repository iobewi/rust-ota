"""Gated *physical* OTA upload, independent flash readback, NO activation.

A file bearing an approval flag is only an execution guard, not a substitute
for the operator's explicit approval of this precise flash write. Never run
this recipe before backup, recovery and the write-region review.
"""
import hashlib
import json
import os
from pathlib import Path
import time

import pytest

from diagnostic import validate_diagnostic
from ota_http import OtaHttp, OtaTransportUncertain
from ota_meta import decode_ota_meta, SECTOR

pytestmark = pytest.mark.bench


def sha_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture
def approved_stage():
    if os.environ.get("OTA_APPROVED_STAGE") != "yes":
        pytest.skip("OTA_APPROVED_STAGE=yes requires prior operator write approval")
    path = os.environ.get("OTA_APPROVAL_FILE")
    expected = os.environ.get("OTA_APPROVAL_SHA256")
    if not path or not expected:
        pytest.fail("Missing private approved plan path/SHA-256 before any bench access")
    if sha_file(path) != expected:
        pytest.fail("Approved plan digest differs before any bench access")
    plan = json.loads(Path(path).read_text())
    required = {
        "schema", "scope", "device", "mcu", "flash_size", "table_offset",
        "backup_file", "backup_sha256", "image_file", "image_sha256",
        "manifest_file", "deployment_id", "baseline_build_id",
        "slot_0", "slot_1", "ota_meta_offset",
    }
    assert isinstance(plan, dict) and required <= set(plan), "Incomplete approval plan"
    assert plan["schema"] == 1 and plan["scope"] == "ota.stage-and-readback"
    assert plan["mcu"] == "esp32c3", "C3 only for this initial qualification"
    assert plan["flash_size"] == 4 * 1024 * 1024, "Unexpected approved geometry"
    assert os.environ.get("BENCH_DEVICE", "esp32-local") == plan["device"]
    for field in ("backup_sha256", "image_sha256"):
        assert isinstance(plan[field], str) and len(plan[field]) == 64
        assert all(c in "0123456789abcdef" for c in plan[field])
    assert os.path.isabs(plan["backup_file"]) and os.path.isabs(plan["image_file"])
    assert os.path.isabs(plan["manifest_file"]), "Test signing manifest must remain private"
    assert Path(plan["backup_file"]).stat().st_size == plan["flash_size"]
    assert sha_file(plan["backup_file"]) == plan["backup_sha256"]
    assert sha_file(plan["image_file"]) == plan["image_sha256"]
    assert isinstance(plan["deployment_id"], str) and plan["baseline_build_id"]
    assert type(plan["table_offset"]) is int and plan["table_offset"] % 4096 == 0
    for label in ("slot_0", "slot_1"):
        slot = plan[label]
        assert set(slot) == {"offset", "size"} and all(
            type(slot[name]) is int for name in ("offset", "size")
        )
        assert slot["offset"] % 4096 == 0 and slot["size"] > 0
        assert slot["offset"] + slot["size"] <= plan["flash_size"]
    assert type(plan["ota_meta_offset"]) is int
    assert plan["ota_meta_offset"] % SECTOR == 0
    assert 0 <= plan["ota_meta_offset"] <= plan["flash_size"] - 2 * SECTOR
    first, second = plan["slot_0"], plan["slot_1"]
    assert (first["offset"] + first["size"] <= second["offset"]
            or second["offset"] + second["size"] <= first["offset"])
    return plan


def _diagnostic(client, *, build, chip, mac, timeout=45):
    """GET-only bounded wait after bench loader returns to the application."""
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            status, body = client.diagnostic()
            if status != 200:
                raise AssertionError(f"Diagnostic HTTP status {status}")
            return validate_diagnostic(body, expected_build=build, expected_mcu=chip,
                                       expected_mac=mac)
        except OtaTransportUncertain as error:
            last = type(error).__name__
            time.sleep(1)
    raise AssertionError(f"Diagnostic unavailable after read-only loader return: {last}")


def test_staged_image_readback_without_activation(approved_stage, ota_campaign):
    plan = approved_stage
    if os.environ.get("OTA_HTTPS_ORIGIN") is None or os.environ.get("OTA_CA_FILE") is None:
        pytest.fail("Missing OTA_HTTPS_ORIGIN or OTA_CA_FILE")
    token = os.environ.get("IOBEWI_OTA_TOKEN")
    if not token:
        pytest.fail("Missing private OTA administration token")
    board = ota_campaign.reserve(ttl=3600)
    identity = board.identify()
    assert identity["chip"] == plan["mcu"]
    assert identity["flash_size"] == plan["flash_size"]
    observed = board.partitions(address=plan["table_offset"])
    by_label = {part["label"]: part for part in observed}
    assert {"ota_0", "ota_1", "otadata", "ota_meta", "config"} <= set(by_label)
    for label, name in (("ota_0", "slot_0"), ("ota_1", "slot_1")):
        p, expected = by_label[label], plan[name]
        assert (p["address"], p["size"]) == (expected["offset"], expected["size"])

    assert by_label["ota_meta"]["address"] == plan["ota_meta_offset"]
    assert by_label["ota_meta"]["size"] == 2 * SECTOR

    # A full 4 MiB private comparison, before ANY OTA application upload.
    baseline = board.read_flash(address=0, size=plan["flash_size"], timeout=600)
    assert hashlib.sha256(baseline).hexdigest() == plan["backup_sha256"], (
        "Current flash does not match verified backup; NO OTA write permitted"
    )
    ota_campaign.write("backup-preflight.json", {
        "flash_sha256": plan["backup_sha256"], "bytes": plan["flash_size"],
        "approval_file_sha256": sha_file(os.environ["OTA_APPROVAL_FILE"]),
    })
    board.renew(ttl=3600)

    app = OtaHttp(os.environ["OTA_HTTPS_ORIGIN"],
                  os.environ["OTA_CA_FILE"], token, timeout=120)
    before = _diagnostic(app, build=plan["baseline_build_id"], chip=plan["mcu"],
                         mac=identity["mac"])
    inactive = 1 - before["running_slot"]
    target = plan[f"slot_{inactive}"]
    image_size = Path(plan["image_file"]).stat().st_size
    assert 0 < image_size <= target["size"] - 4096, (
        "Image may overlap reserved proof sector"
    )
    manifest = Path(plan["manifest_file"]).read_text(encoding="ascii").strip()
    OtaHttp.validate_manifest(manifest)

    # This is the *first write*. It must have been explicitly authorized.
    # Never re-submit after a lost POST or timeout, even if a later read seems safe.
    status, response = app.upload(
        Path(plan["image_file"]), plan["deployment_id"],
        manifest=manifest, expected_sha256=plan["image_sha256"],
        max_bytes=target["size"] - 4096,
    )
    assert (status, response) == (200, b"staged"), (
        f"Upload not staged: HTTP {status}, response withheld"
    )

    # Independent physical readback of precisely the transmitted image bytes.
    data = board.read_flash(address=target["offset"], size=image_size, timeout=600)
    assert hashlib.sha256(data).hexdigest() == plan["image_sha256"], (
        "Written slot digest disagrees with approved image"
    )
    # Independent durable store read. A 200 staged alone does not prove an
    # OTM1 commit: decode the *newest valid* OTSF frame from flash.
    store_raw = board.read_flash(
        address=plan["ota_meta_offset"], size=2 * SECTOR, timeout=600
    )
    store = decode_ota_meta(store_raw)
    assert store["kind"] == "Payload", "No committed OTSF/OTM1 publication"
    record = store["metadata"]
    assert record["stage"] == "Written", "Staged transaction not durable"
    assert record["slot"] == f"ota_{inactive}"
    assert record["deployment_id"] == plan["deployment_id"]
    assert record["size"] == image_size
    assert record["digest"] == "sha256:" + plan["image_sha256"]

    ota_campaign.write("staged-readback.json", {
        "running_slot_before_upload": before["running_slot"],
        "target_slot": inactive,
        "target_offset": target["offset"],
        "bytes_verified": len(data),
        "image_sha256": plan["image_sha256"],
        "http_staged": True,
        "independent_flash_readback": True,
        "activation_executed": False,
        "otm1_durable_publication_independently_verified": True,
        "otm1_frame_copy": store["copy"],
        "otm1_frame_sequence": store["sequence"],
        "otm1_degraded": store["degraded"],
        "ota_meta_sha256": hashlib.sha256(store_raw).hexdigest(),
    })
