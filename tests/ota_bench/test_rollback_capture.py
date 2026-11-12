"""Offline forensic rollback recipe from independently captured flash evidence.

No bench operations, no network, no fault injection. Explicitly requires the
runtime identity after rollback: BOOT/OTM1 bytes alone cannot prove that the
fallback firmware actually executed. This test does not authenticate the app.
"""
import json
import os
from pathlib import Path

import pytest

from diagnostic import validate_diagnostic
from rollback_proof import require_rollback_evidence, verified_capture

pytestmark = pytest.mark.ota_preparation


def test_rollback_from_private_capture_manifest():
    manifest_path = os.environ.get("OTA_ROLLBACK_EVIDENCE_MANIFEST")
    if not manifest_path:
        pytest.skip("Set OTA_ROLLBACK_EVIDENCE_MANIFEST for private captured evidence")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    assert manifest.get("schema") == 1, "Unknown rollback evidence manifest schema"
    assert manifest.get("scope") == "ota.rollback-forensic", "Wrong evidence scope"
    assert manifest.get("mcu") in ("esp32c3", "esp32s3")
    fallback_slot = manifest.get("fallback_slot")
    assert type(fallback_slot) is int and fallback_slot in (0, 1)
    assert isinstance(manifest.get("fallback_build_id"), str)
    assert manifest["fallback_build_id"]
    assert isinstance(manifest.get("station_mac"), str)
    assert manifest["station_mac"]
    files = manifest.get("files")
    assert isinstance(files, dict)
    expected = {
        "before_otadata", "after_otadata",
        "before_ota_meta", "after_ota_meta",
        "final_diagnostic",
    }
    assert set(files) == expected, "Incomplete or unexpected evidence inventory"
    evidence = {}
    for name in expected:
        source = files[name]
        assert isinstance(source, dict) and set(source) == {"path", "sha256"}
        assert Path(source["path"]).is_absolute(), "Use private absolute paths"
        if name == "final_diagnostic":
            raw = verified_capture(source["path"], source["sha256"],
                                   expected_size=Path(source["path"]).stat().st_size)
            assert 0 < len(raw) <= 4096, "Diagnostic capture out of bounds"
        else:
            raw = verified_capture(source["path"], source["sha256"])
        evidence[name] = raw
    runtime = validate_diagnostic(
        evidence["final_diagnostic"],
        expected_build=manifest["fallback_build_id"],
        expected_mcu=manifest["mcu"],
        expected_mac=manifest["station_mac"],
    )
    assert runtime["running_slot"] == fallback_slot, (
        "Runtime identity does not match expected rollback fallback slot"
    )
    outcome = require_rollback_evidence(
        evidence["before_otadata"], evidence["after_otadata"],
        evidence["before_ota_meta"], evidence["after_ota_meta"],
        fallback_slot=fallback_slot,
    )
    assert outcome["fallback_slot"] == runtime["running_slot"]
    assert outcome["rejected_state"] in ("Invalid", "Aborted")
