"""Offline proof tests; fixtures model snapshots, never a physical rollback."""
import hashlib

import pytest
from rollback_proof import verified_capture, require_rollback_evidence
from test_boot_transitions import flash, record
from test_ota_meta import pair, frame, otm1


def _stores():
    old = pair(frame(otm1(
        stage=2, slot="ota_1", deployment="B",
        digest="sha256:" + "b" * 64, size=1024,
        active_digest="sha256:" + "a" * 64, active_deployment="A",
    ), 4))
    new = pair(frame(otm1(
        stage=0,
        active_digest="sha256:" + "a" * 64,
        active_deployment="A",
    ), 5))
    return old, new


@pytest.mark.parametrize("rejected_state", [3, 4])
def test_valid_rejected_candidate_preserves_active_identity(rejected_state):
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, rejected_state))
    old_store, new_store = _stores()
    result = require_rollback_evidence(
        before, after, old_store, new_store, fallback_slot=0
    )
    assert result["fallback_slot"] == 0
    assert result["rejected_state"] in ("Invalid", "Aborted")
    assert result["previous_active_deployment"] == "A"
    assert result["runtime_fallback_independently_observed"] is False


def test_unconfirmed_candidate_is_not_a_completed_rollback():
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, 1))
    old_store, new_store = _stores()
    with pytest.raises(AssertionError, match="not rejected"):
        require_rollback_evidence(
            before, after, old_store, new_store, fallback_slot=0
        )


def test_rollback_cannot_promote_failed_candidate():
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, 4))
    old, _ = _stores()
    wrong = pair(frame(otm1(
        stage=0, active_digest="sha256:" + "b" * 64,
        active_deployment="B",
    ), 5))
    with pytest.raises(AssertionError, match="active deployment"):
        require_rollback_evidence(before, after, old, wrong, fallback_slot=0)


def test_corrupted_metadata_is_not_accepted():
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, 4))
    old, _ = _stores()
    with pytest.raises(AssertionError, match="unreadable"):
        require_rollback_evidence(
            before, after, old, b"\x00" * 8192, fallback_slot=0
        )


def test_capture_sha256_and_length_are_mandatory(tmp_path):
    image = tmp_path / "read.bin"
    image.write_bytes(b"example")
    correct = hashlib.sha256(image.read_bytes()).hexdigest()
    assert verified_capture(image, correct, expected_size=7) == b"example"
    with pytest.raises(AssertionError, match="evidence manifest"):
        verified_capture(image, "0" * 64, expected_size=7)
    with pytest.raises(AssertionError, match="size"):
        verified_capture(image, correct, expected_size=8)
    with pytest.raises(ValueError, match="Invalid expected SHA-256"):
        verified_capture(image, "x" * 64, expected_size=7)
