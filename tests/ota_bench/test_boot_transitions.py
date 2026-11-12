"""Host tests prove assertion sensitivity, not physical OTA behavior."""
import struct
import zlib

import pytest
from boot_metadata import COMMIT, SECTOR
from boot_transitions import require_confirmed_transition, require_rollback


def record(seq, state):
    payload = struct.pack("<II", seq, state) + b"BOOT" + struct.pack("<I", 2)
    ext_crc = zlib.crc32(payload, 0xFFFFFFFF)
    seq_crc = zlib.crc32(struct.pack("<I", seq), 0xFFFFFFFF)
    return struct.pack("<I4sIIIIII", seq, b"BOOT", 2, ext_crc,
                       0xFFFFFFFF, COMMIT, state, seq_crc)


def flash(first=None, second=None):
    def sector(record_bytes):
        if record_bytes is None:
            return b"\xff" * SECTOR
        return record_bytes + b"\xff" * (SECTOR - 32)
    return sector(first) + sector(second)


def test_confirmed_a_to_b():
    a = flash(record(1, 2), None)
    b = flash(record(1, 2), record(2, 2))
    outcome = require_confirmed_transition(a, b, from_slot=0, to_slot=1)
    assert outcome["candidate"]["slot"] == 1
    assert outcome["candidate"]["state"] == "Valid"
    assert outcome["fallback_preserved"] is True


def test_confirmed_b_to_a():
    start = flash(record(1, 2), record(2, 2))
    end = flash(record(3, 2), record(2, 2))
    result = require_confirmed_transition(start, end, from_slot=1, to_slot=0)
    assert result["candidate"]["sequence"] == 3


@pytest.mark.parametrize("state", [0, 1, 3, 4])
def test_unconfirmed_or_rejected_candidate_not_accepted_as_nominal(state):
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, state))
    with pytest.raises(AssertionError):
        require_confirmed_transition(before, after, from_slot=0, to_slot=1)


def test_old_confirmed_slot_cannot_disappear():
    before = flash(record(1, 2), None)
    after = flash(None, record(2, 2))
    with pytest.raises(AssertionError, match="confirmed entry"):
        require_confirmed_transition(before, after, from_slot=0, to_slot=1)


@pytest.mark.parametrize("rejection", [3, 4])
def test_rollback_preserves_fallback(rejection):
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, rejection))
    outcome = require_rollback(before, after, fallback_slot=0)
    assert outcome["rejected"]["state"] in ("Invalid", "Aborted")


def test_pending_is_not_a_successful_rollback():
    before = flash(record(1, 2), None)
    after = flash(record(1, 2), record(2, 1))
    with pytest.raises(AssertionError, match="not rejected"):
        require_rollback(before, after, fallback_slot=0)


def test_rollback_requires_previous_confirmed_entry():
    before = flash(None, record(2, 0))
    after = flash(record(1, 2), record(2, 4))
    with pytest.raises(AssertionError, match="confirmed entry"):
        require_rollback(before, after, fallback_slot=0)
