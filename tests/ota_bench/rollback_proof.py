"""Offline-only rollback proof from physical snapshots captured via the bench.

No fault injection, serial access, flash write, or replay. The caller must
provide independently collected before/after dumps and their SHA-256.
"""
import hashlib
from pathlib import Path

from boot_transitions import require_rollback
from ota_meta import decode_ota_meta


def verified_capture(path, expected_sha256, *, expected_size=8192) -> bytes:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("Expected SHA-256 must be 64 lowercase hexadecimal chars")
    if any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("Invalid expected SHA-256")
    content = Path(path).read_bytes()
    assert len(content) == expected_size, "Unexpected flash capture size"
    assert hashlib.sha256(content).hexdigest() == expected_sha256, (
        "Flash capture differs from evidence manifest"
    )
    return content


def require_rollback_evidence(
    before_boot: bytes, after_boot: bytes,
    before_store: bytes, after_store: bytes, *, fallback_slot: int,
) -> dict:
    """Require valid durable fallback and no fabricated active deployment.

    The OTA store may retain an unresolved intent depending on how reconciliation
    completes. Do not demand a specific staged state without a verified contract.
    """
    boot = require_rollback(
        before_boot, after_boot, fallback_slot=fallback_slot
    )
    old = decode_ota_meta(before_store)
    new = decode_ota_meta(after_store)
    assert old["kind"] == "Payload" and new["kind"] == "Payload", (
        "OTA metadata is unreadable; cannot qualify rollback"
    )
    old_meta = old["metadata"]
    new_meta = new["metadata"]
    assert old_meta["active_deployment_id"] == new_meta["active_deployment_id"], (
        "Rejected candidate changed active deployment identity"
    )
    assert old_meta["active_digest"] == new_meta["active_digest"], (
        "Rejected candidate changed active image digest"
    )
    assert new_meta["stage"] != "Written", (
        "Rollback left candidate marked as newly staged"
    )
    return {
        "fallback_slot": boot["fallback"]["slot"],
        "rejected_state": boot["rejected"]["state"],
        "previous_active_deployment": old_meta["active_deployment_id"],
        "otm1_new_stage": new_meta["stage"],
        "boot_metadata_after_sha256": hashlib.sha256(after_boot).hexdigest(),
        "ota_metadata_after_sha256": hashlib.sha256(after_store).hexdigest(),
        "runtime_fallback_independently_observed": False,
        "cryptographic_authenticity_proven": False,
    }
