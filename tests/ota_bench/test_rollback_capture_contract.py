"""Host-only adversarial tests for the captured rollback recipe."""
import hashlib
import json

import pytest

from test_boot_transitions import flash, record
from test_ota_meta import frame, otm1, pair
from test_rollback_capture import test_rollback_from_private_capture_manifest as verify_capture


def make_manifest(tmp_path, *, wrong_runtime=False):
    before_boot = flash(record(1, 2), None)
    after_boot = flash(record(1, 2), record(2, 4))
    before_store = pair(frame(otm1(
        stage=2, slot="ota_1", deployment="B",
        digest="sha256:" + "b" * 64, size=123,
        active_digest="sha256:" + "a" * 64, active_deployment="A",
    ), 9))
    after_store = pair(frame(otm1(
        stage=0, active_digest="sha256:" + "a" * 64,
        active_deployment="A",
    ), 10))
    diag = {
        "schema": 2, "build_id": "other" if wrong_runtime else "fallback-A",
        "mcu": "esp32c3", "station_mac": "02:01:23:45:67:89",
        "running_slot": 0,
        "boot_entries": [
            {"kind": "Ok", "sequence": 1, "state": 2},
            {"kind": "Ok", "sequence": 2, "state": 4},
        ],
        "otm1_observed": False, "image_authenticated": False,
    }
    contents = {
        "before_otadata": before_boot,
        "after_otadata": after_boot,
        "before_ota_meta": before_store,
        "after_ota_meta": after_store,
        "final_diagnostic": json.dumps(diag).encode("utf-8"),
    }
    files = {}
    for name, content in contents.items():
        path = tmp_path / (name + ".bin")
        path.write_bytes(content)
        files[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    manifest = {
        "schema": 1, "scope": "ota.rollback-forensic",
        "mcu": "esp32c3", "fallback_slot": 0,
        "fallback_build_id": "fallback-A",
        "station_mac": "02:01:23:45:67:89",
        "files": files,
    }
    file = tmp_path / "manifest.json"
    file.write_text(json.dumps(manifest))
    return file, files


def test_valid_forensic_capture(tmp_path, monkeypatch):
    path, _ = make_manifest(tmp_path)
    monkeypatch.setenv("OTA_ROLLBACK_EVIDENCE_MANIFEST", str(path))
    verify_capture()


def test_tampered_flash_capture_rejected(tmp_path, monkeypatch):
    path, files = make_manifest(tmp_path)
    flash_path = files["after_ota_meta"]["path"]
    with open(flash_path, "r+b") as stream:
        stream.seek(0)
        stream.write(b"NOPE")
    monkeypatch.setenv("OTA_ROLLBACK_EVIDENCE_MANIFEST", str(path))
    with pytest.raises(AssertionError, match="evidence manifest"):
        verify_capture()


def test_unexpected_running_build_rejected(tmp_path, monkeypatch):
    path, _ = make_manifest(tmp_path, wrong_runtime=True)
    monkeypatch.setenv("OTA_ROLLBACK_EVIDENCE_MANIFEST", str(path))
    with pytest.raises(AssertionError, match="Unexpected firmware build"):
        verify_capture()


def test_no_evidence_is_not_a_pass(monkeypatch):
    monkeypatch.delenv("OTA_ROLLBACK_EVIDENCE_MANIFEST", raising=False)
    with pytest.raises(pytest.skip.Exception):
        verify_capture()
