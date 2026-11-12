"""Read-only independent OTSF/OTM1 parser, from rust-ota pinned storage contract.

OTSF frame: common/update/src/frame_store.rs
OTM1 payload: common/update/src/compat/otm1.rs
Selection: common/update/src/double_copy.rs

CRC detects corruption but does not provide authentication.
"""
from __future__ import annotations

import struct
import zlib

SECTOR = 4096
FRAME_MAX = 528
PAYLOAD_MAX = 512
STAGES = {0: "None", 1: "Written", 2: "Activating"}


def decode_otm1(payload: bytes) -> dict:
    if not 19 <= len(payload) <= PAYLOAD_MAX or payload[:4] != b"OTM1":
        raise ValueError("Unknown OTM1 record")
    if payload[4] not in STAGES:
        raise ValueError("Unknown OTM1 stage")
    size = struct.unpack_from("<I", payload, 5)[0]
    lengths = struct.unpack_from("<5H", payload, 9)
    if any(n > limit for n, limit in zip(lengths, (8, 71, 128, 71, 128))):
        raise ValueError("OTM1 string exceeds declared bound")
    if 19 + sum(lengths) != len(payload):
        raise ValueError("OTM1 field lengths disagree with total")
    at = 19
    decoded = []
    for length in lengths:
        decoded.append(payload[at:at + length].decode("utf-8", errors="strict"))
        at += length
    slot, digest, deployment, active_digest, active_deployment = decoded
    return {
        "stage": STAGES[payload[4]], "size": size,
        "slot": slot, "digest": digest, "deployment_id": deployment,
        "active_digest": active_digest, "active_deployment_id": active_deployment,
    }


def decode_frame(raw: bytes) -> dict:
    if len(raw) != FRAME_MAX:
        raise ValueError("OTSF frame must match 528-byte reader")
    if all(byte == 0xff for byte in raw):
        return {"kind": "Blank"}
    if raw[:4] != b"OTSF" or raw[4] != 1 or raw[5] != 0:
        return {"kind": "Corrupt"}
    length = struct.unpack_from("<H", raw, 6)[0]
    if length > PAYLOAD_MAX:
        return {"kind": "Corrupt"}
    aligned = (length + 3) & ~3
    crc_at = 12 + aligned
    expected = struct.unpack_from("<I", raw, crc_at)[0]
    actual = zlib.crc32(raw[:crc_at])
    if expected != actual or any(raw[12 + length:crc_at]):
        return {"kind": "Corrupt"}
    return {
        "kind": "Ok",
        "sequence": struct.unpack_from("<I", raw, 8)[0],
        "payload": raw[12:12 + length],
    }


def _newer(a: int, b: int) -> bool:
    """u32 wrapping serial arithmetic from double_copy.rs."""
    delta = (a - b) & 0xFFFFFFFF
    return 0 < delta < 0x80000000


def decode_ota_meta(raw: bytes) -> dict:
    if len(raw) != 2 * SECTOR:
        raise ValueError("ota_meta requires two 4 KiB sectors")
    frames = [
        decode_frame(raw[:FRAME_MAX]),
        decode_frame(raw[SECTOR:SECTOR + FRAME_MAX]),
    ]
    valid = [i for i, frame in enumerate(frames) if frame["kind"] == "Ok"]
    if not valid:
        return {
            "kind": "Blank" if all(f["kind"] == "Blank" for f in frames)
            else "Corrupt",
            "copies": [frame["kind"] for frame in frames],
        }
    chosen = valid[0]
    if len(valid) == 2 and _newer(frames[1]["sequence"], frames[0]["sequence"]):
        chosen = 1
    record = frames[chosen]
    try:
        metadata = decode_otm1(record["payload"])
    except (ValueError, UnicodeError) as error:
        # OTSF may be structurally valid but payload OTM1 invalid: fail closed
        # in the qualification tool, rather than claiming a valid transaction.
        raise ValueError("Valid OTSF frame contains invalid OTM1") from error
    return {
        "kind": "Payload", "sequence": record["sequence"], "copy": chosen,
        "degraded": len(valid) != 2,
        "copies": [frame["kind"] for frame in frames],
        "metadata": metadata,
    }
