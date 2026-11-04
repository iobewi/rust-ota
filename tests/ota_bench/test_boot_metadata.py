"""Independent host tests for the exact BOOT v2 decoder."""
import struct
import zlib

import pytest

from boot_metadata import (
    COMMIT, SECTOR, decode_record, decode_otadata, assert_no_unconfirmed_new_selection,
)


def golden(seq=1, state=2):
    # Independent encoder from common/boot/tools/otadata_vectors.py.
    magic, version = b"BOOT", 2
    ext = zlib.crc32(
        struct.pack("<II", seq, state) + magic + struct.pack("<I", version),
        0xFFFFFFFF,
    )
    return struct.pack(
        "<I4sIIIIII", seq, magic, version, ext, 0xFFFFFFFF,
        COMMIT, state, zlib.crc32(struct.pack("<I", seq), 0xFFFFFFFF),
    )


@pytest.mark.parametrize("seq, state, expected", [
    (1, 2, "Valid"), (2, 0, "New"), (2, 1, "PendingVerify"),
    (2, 3, "Invalid"), (2, 4, "Aborted"), (3, 2, "Valid"),
])
def test_exact_records(seq, state, expected):
    assert decode_record(golden(seq, state)) == {
        "kind": "Ok", "sequence": seq, "state": expected,
        "slot": (seq - 1) % 2,
    }


@pytest.mark.parametrize("offset", [0, 4, 8, 12, 16, 20, 24, 28])
def test_corruption_of_each_field_is_detected(offset):
    raw = bytearray(golden())
    raw[offset] ^= 0x01
    assert decode_record(bytes(raw)) == {"kind": "Corrupt"}


@pytest.mark.parametrize("field", [b"XXXX", b"BOOT"])
def test_blank_and_uncommitted(field):
    assert decode_record(b"\xff" * 32) == {"kind": "Blank"}
    raw = bytearray(golden())
    raw[4:8] = field
    raw[20:24] = b"\xff" * 4
    assert decode_record(bytes(raw)) == {"kind": "Corrupt"}


def test_sector_boundaries_and_stable_baseline():
    data = golden(1, 2) + b"\xff" * (SECTOR - 32)
    data += b"\xff" * SECTOR
    assert decode_otadata(data)[1] == {"kind": "Blank"}
    assert assert_no_unconfirmed_new_selection(data)[0]["state"] == "Valid"


def test_new_candidate_does_not_count_as_confirmed():
    first = golden(1, 2) + b"\xff" * (SECTOR - 32)
    second = golden(2, 0) + b"\xff" * (SECTOR - 32)
    with pytest.raises(AssertionError, match="unconfirmed"):
        assert_no_unconfirmed_new_selection(first + second)


def test_missing_valid_is_rejected():
    data = golden(2, 1) + b"\xff" * (SECTOR - 32) + b"\xff" * SECTOR
    with pytest.raises(AssertionError, match="No confirmed"):
        assert_no_unconfirmed_new_selection(data)


def test_invalid_geometry_is_not_silently_accepted():
    with pytest.raises(ValueError, match="exactly"):
        decode_otadata(b"\xff" * SECTOR)
    with pytest.raises(ValueError, match="32"):
        decode_record(b"\xff" * 31)
