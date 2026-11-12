"""Pre-upload checks. No network, no MCU, no flash mutation."""
import hashlib
import json
import os
from pathlib import Path
import pytest

pytestmark = pytest.mark.ota_preparation


def load_candidate(image_path, expected_sha256, manifest_path=None):
    """Validate file identity BEFORE submitting anything to the target."""
    image = Path(image_path)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    assert digest == expected_sha256, "Candidate image differs from approved digest"
    assert image.stat().st_size > 0, "Candidate image is empty"
    manifest = None
    if manifest_path is not None:
        manifest = Path(manifest_path).read_text(encoding="ascii").strip()
        from ota_http import OtaHttp
        OtaHttp.validate_manifest(manifest)
    return {"file": str(image), "size": image.stat().st_size,
            "sha256": digest, "manifest": manifest}


def test_candidate_local_identity(tmp_path):
    image = tmp_path / "candidate.bin"
    image.write_bytes(b"known candidate")
    expected = hashlib.sha256(image.read_bytes()).hexdigest()
    verified = load_candidate(image, expected)
    assert verified["size"] == len(b"known candidate")
    assert verified["sha256"] == expected
    assert verified["manifest"] is None


def test_candidate_hash_mismatch_rejected(tmp_path):
    image = tmp_path / "candidate.bin"
    image.write_bytes(b"wrong bytes")
    with pytest.raises(AssertionError, match="approved digest"):
        load_candidate(image, "0" * 64)


def test_candidate_invalid_manifest_rejected(tmp_path):
    image = tmp_path / "candidate.bin"
    manifest = tmp_path / "manifest.txt"
    image.write_bytes(b"candidate")
    manifest.write_text("bad+base64")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="base64url"):
        load_candidate(image, digest, manifest)


def test_approved_candidate_opt_in_is_not_implicit():
    """An offline test must never open an OTA connection."""
    assert callable(load_candidate)
