"""Host-only negative checks: detect false PASS on refusal or flash mutation."""
import struct
import zlib

import pytest

from boot_metadata import COMMIT, SECTOR
from ota_meta import SECTOR as META_SECTOR
from refusal_assertions import require_exact_refusal, require_unchanged_persistent_state


def _boot(seq=1, state=2):
    ext = zlib.crc32(
        struct.pack("<II", seq, state) + b"BOOT" + struct.pack("<I", 2),
        0xFFFFFFFF,
    )
    return struct.pack(
        "<I4sIIIIII", seq, b"BOOT", 2, ext, 0xFFFFFFFF, COMMIT,
        state, zlib.crc32(struct.pack("<I", seq), 0xFFFFFFFF),
    )


def _otadata():
    return _boot() + b"\xff" * (SECTOR - 32) + b"\xff" * SECTOR


def _frame(payload=b"OTM1" + b"\0" * 15):
    body = b"OTSF" + bytes([1, 0]) + struct.pack("<H", len(payload))
    body += struct.pack("<I", 1) + payload
    body += b"\0" * (-len(payload) % 4)
    return body + struct.pack("<I", zlib.crc32(body))


def _ota_meta():
    record = _frame()
    return record + b"\xff" * (META_SECTOR - len(record)) + b"\xff" * META_SECTOR


@pytest.mark.parametrize("status,body", [
    (400, b"invalid request"),
    (400, b"activation requires an empty body"),
    (400, b"length and sha256 digest required"),
    (401, b"unauthorized"),
    (409, b"activation refused"),
    (409, b"upload refused or verification failed"),
])
def test_exact_refusal_codes(status, body):
    require_exact_refusal((status, body), status=status, body=body)


@pytest.mark.parametrize("bad", [
    (200, b"invalid request"),
    (409, b"invalid request"),
    (400, b"staged"),
    (400, b""),
])
def test_unexpected_response_must_fail(bad):
    with pytest.raises(AssertionError):
        require_exact_refusal(bad, status=400, body=b"invalid request")


def test_clean_before_and_after_bytes():
    boot, meta = _otadata(), _ota_meta()
    result = require_unchanged_persistent_state(boot, boot, meta, meta)
    assert result["durable_bytes_unchanged"] is True
    assert result["flash_write_count_proven_zero"] is False


def test_rejected_command_must_not_change_otadata():
    boot = _otadata()
    new = bytearray(boot)
    new[32] = 0
    with pytest.raises(AssertionError, match="boot selection"):
        require_unchanged_persistent_state(boot, bytes(new), _ota_meta(), _ota_meta())


def test_rejected_command_must_not_change_otm1():
    meta = _ota_meta()
    updated = bytearray(meta)
    updated[META_SECTOR + 1] = 0x00
    with pytest.raises(AssertionError, match="OTA transaction"):
        require_unchanged_persistent_state(_otadata(), _otadata(), meta, bytes(updated))


def test_identical_corrupt_snapshots_must_not_pass():
    broken = b"\0" * (2 * SECTOR)
    with pytest.raises(AssertionError, match="confirmed fallback"):
        require_unchanged_persistent_state(broken, broken, _ota_meta(), _ota_meta())


def test_identical_corrupt_otm1_snapshots_must_not_pass():
    broken = b"\0" * (2 * META_SECTOR)
    with pytest.raises(AssertionError, match="unreadable"):
        require_unchanged_persistent_state(_otadata(), _otadata(), broken, broken)
