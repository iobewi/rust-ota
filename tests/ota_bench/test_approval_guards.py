"""Offline adversarial checks of destructive-test admission guards."""
import hashlib
import json

import pytest

from test_staged_image import approved_stage


def _admit():
    # Call the fixture implementation as an offline pure function. Never call
    # the bench, OTA application, or its POST operation.
    return approved_stage.__wrapped__()


def _valid_plan(tmp_path):
    flash = tmp_path / "flash.bin"
    image = tmp_path / "candidate.bin"
    manifest = tmp_path / "envelope.txt"
    flash.write_bytes(b"\xff" * (4 * 1024 * 1024))
    image.write_bytes(b"test image")
    manifest.write_text("YWJj")
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "schema": 1, "scope": "ota.stage-and-readback",
        "device": "esp32-local", "mcu": "esp32c3",
        "flash_size": 4 * 1024 * 1024, "table_offset": 0x8000,
        "backup_file": str(flash), "backup_sha256": digest(flash),
        "image_file": str(image), "image_sha256": digest(image),
        "manifest_file": str(manifest), "deployment_id": "qual-B-01",
        "baseline_build_id": "qual-A-01",
        "slot_0": {"offset": 0x20000, "size": 0x180000},
        "slot_1": {"offset": 0x1a0000, "size": 0x180000},
    }


def _set_plan(monkeypatch, tmp_path, plan):
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(plan))
    monkeypatch.setenv("OTA_APPROVAL_FILE", str(path))
    monkeypatch.setenv("OTA_APPROVAL_SHA256",
                       hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setenv("OTA_APPROVED_STAGE", "yes")
    monkeypatch.setenv("BENCH_DEVICE", "esp32-local")
    return path


def test_unapproved_stage_skips_before_any_bench_access(monkeypatch):
    monkeypatch.delenv("OTA_APPROVED_STAGE", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _admit()


def test_missing_approval_fails_locally(monkeypatch):
    monkeypatch.setenv("OTA_APPROVED_STAGE", "yes")
    monkeypatch.delenv("OTA_APPROVAL_FILE", raising=False)
    monkeypatch.delenv("OTA_APPROVAL_SHA256", raising=False)
    with pytest.raises(pytest.fail.Exception, match="Missing private"):
        _admit()


def test_wrong_approval_digest_blocks(monkeypatch, tmp_path):
    _set_plan(monkeypatch, tmp_path, _valid_plan(tmp_path))
    monkeypatch.setenv("OTA_APPROVAL_SHA256", "0" * 64)
    with pytest.raises(pytest.fail.Exception, match="digest differs"):
        _admit()


@pytest.mark.parametrize("change", [
    {"scope": "ota.activate-and-confirm"},
    {"device": "another-board"},
    {"flash_size": 8 * 1024 * 1024},
])
def test_unexpected_approved_parameters_rejected(monkeypatch, tmp_path, change):
    plan = _valid_plan(tmp_path)
    plan.update(change)
    _set_plan(monkeypatch, tmp_path, plan)
    with pytest.raises(AssertionError):
        _admit()


def test_private_backup_hash_must_match(monkeypatch, tmp_path):
    plan = _valid_plan(tmp_path)
    plan["backup_sha256"] = "0" * 64
    _set_plan(monkeypatch, tmp_path, plan)
    with pytest.raises(AssertionError):
        _admit()


def test_exact_plan_passes_offline_admission_only(monkeypatch, tmp_path):
    plan = _valid_plan(tmp_path)
    _set_plan(monkeypatch, tmp_path, plan)
    assert _admit() == plan
