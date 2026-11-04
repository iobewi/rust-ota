"""Read-only ESP32 boot metadata v2 decoder.

Cross-check: common/boot/src/lib.rs and common/boot/tools/otadata_vectors.py
at the pinned rust-ota revision. A decodable metadata record is NOT a boot
authenticity proof, a running-slot observation, or an OTM1 confirmation proof.
"""
from __future__ import annotations

import struct
import zlib

SECTOR = 4096
ENTRY = 32
MAGIC = b"BOOT"
VERSION = 2
COMMIT = 0x5AC3A53C
STATES = {0: "New", 1: "PendingVerify", 2: "Valid", 3: "Invalid", 4: "Aborted"}


def _crc(data: bytes) -> int:
    return zlib.crc32(data, 0xFFFFFFFF)


def decode_record(raw: bytes) -> dict:
    if len(raw) != ENTRY:
        raise ValueError("Boot record must be 32 bytes")
    if raw == b"\xff" * ENTRY:
        return {"kind": "Blank"}
    seq, magic, version, ext_crc, reserved, commit, state, idf_crc = struct.unpack(
        "<I4sIIIIII", raw
    )
    ext_data = struct.pack("<II", seq, state) + MAGIC + struct.pack("<I", VERSION)
    valid = (
        seq not in (0, 0xFFFFFFFF)
        and state in STATES
        and magic == MAGIC
        and version == VERSION
        and ext_crc == _crc(ext_data)
        and reserved == 0xFFFFFFFF
        and commit == COMMIT
        and idf_crc == _crc(struct.pack("<I", seq))
    )
    if not valid:
        return {"kind": "Corrupt"}
    return {
        "kind": "Ok",
        "sequence": seq,
        "state": STATES[state],
        # ESP32 A/B select is (sequence - 1) modulo number of slots.
        "slot": (seq - 1) % 2,
    }


def decode_otadata(data: bytes) -> list[dict]:
    if len(data) != 2 * SECTOR:
        raise ValueError("otadata v2 requires exactly two 4 KiB sectors")
    return [
        decode_record(data[0:ENTRY]),
        decode_record(data[SECTOR:SECTOR + ENTRY]),
    ]


def assert_no_unconfirmed_new_selection(data: bytes) -> list[dict]:
    """Assert there is no *newly committed* unconfirmed entry in the snapshot.

    Only use for a baseline explicitly expected to be stable. This is not a
    general OTA policy; transient states are valid during a normal update.
    """
    records = decode_otadata(data)
    assert any(item["kind"] == "Ok" and item["state"] == "Valid" for item in records), (
        "No confirmed boot metadata entry"
    )
    assert not any(
        item["kind"] == "Ok"
        and item["state"] in ("New", "PendingVerify")
        for item in records
    ), "A candidate is still unconfirmed"
    return records
