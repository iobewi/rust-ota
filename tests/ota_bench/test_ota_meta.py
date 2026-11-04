"""Independent host vectors and adversarial corruption cases for OTSF/OTM1."""
import struct
import zlib

import pytest
from ota_meta import (
    FRAME_MAX, SECTOR, decode_frame, decode_ota_meta, decode_otm1,
)


def otm1(*, stage=0, slot="", digest="", deployment="", active_digest="",
         active_deployment="", size=0):
    fields = [f.encode("utf-8") for f in (
        slot, digest, deployment, active_digest, active_deployment
    )]
    return (
        b"OTM1" + bytes([stage]) + struct.pack("<I", size)
        + struct.pack("<5H", *(len(field) for field in fields))
        + b"".join(fields)
    )


def frame(payload, seq=1):
    body = (
        b"OTSF" + bytes([1, 0]) + struct.pack("<H", len(payload))
        + struct.pack("<I", seq) + payload
    )
    body += b"\0" * ((-len(payload)) % 4)
    return body + struct.pack("<I", zlib.crc32(body))


def pair(a=None, b=None):
    def sector(item):
        return b"\xff" * SECTOR if item is None else item + b"\xff" * (SECTOR-len(item))
    return sector(a) + sector(b)


def test_golden_legacy_otm1_payload():
    legacy = (
        b"OTM1\x01\x00\x04\x00\x00"
        b"\x05\x00\x00\x00\x08\x00\x00\x00\x00\x00"
        b"ota_1deploy-1"
    )
    assert decode_otm1(legacy)["stage"] == "Written"
    assert decode_otm1(legacy)["slot"] == "ota_1"
    assert decode_otm1(legacy)["deployment_id"] == "deploy-1"


def test_factory_provisioned_default_has_empty_stage():
    raw = pair(frame(otm1()))
    result = decode_ota_meta(raw)
    assert result["kind"] == "Payload"
    assert (result["sequence"], result["copy"], result["degraded"]) == (1, 0, True)
    assert result["metadata"]["stage"] == "None"


def test_written_then_confirmed_on_newer_copy():
    written = otm1(stage=1, slot="ota_1", digest="sha256:" + "a" * 64,
                   deployment="B", size=8096)
    confirmed = otm1(stage=0, active_digest="sha256:" + "a" * 64,
                     active_deployment="B")
    result = decode_ota_meta(pair(frame(written, 9), frame(confirmed, 10)))
    assert result["copy"] == 1
    assert not result["degraded"]
    assert result["metadata"]["stage"] == "None"
    assert result["metadata"]["active_deployment_id"] == "B"


def test_latest_valid_survives_torn_other_copy():
    older = frame(otm1(stage=1, slot="ota_1"), 9)
    damaged = bytearray(frame(otm1(stage=2, slot="ota_1"), 10))
    damaged[14] ^= 0x40
    result = decode_ota_meta(pair(older, bytes(damaged)))
    assert result["copy"] == 0
    assert result["degraded"]
    assert result["copies"] == ["Ok", "Corrupt"]


def test_two_corrupt_copies_fail_closed():
    raw = pair(b"bad", b"bad")
    assert decode_ota_meta(raw)["kind"] == "Corrupt"


def test_two_blank_copies_are_distinct_from_corruption():
    assert decode_ota_meta(pair())["kind"] == "Blank"


def test_sequence_wrap_selects_zero_over_max():
    first = frame(otm1(stage=1), 0xFFFFFFFF)
    second = frame(otm1(stage=2), 0)
    result = decode_ota_meta(pair(first, second))
    assert result["copy"] == 1
    assert result["metadata"]["stage"] == "Activating"


@pytest.mark.parametrize("patch", ["magic", "version", "reserved", "length", "crc", "padding"])
def test_corrupted_frame_is_not_accepted(patch):
    payload = otm1()
    data = bytearray(frame(payload))
    if patch == "magic":
        data[0] ^= 1
    elif patch == "version":
        data[4] = 2
    elif patch == "reserved":
        data[5] = 1
    elif patch == "length":
        data[6:8] = struct.pack("<H", 513)
    elif patch == "crc":
        data[-1] ^= 1
    else:
        # OTM1 default length 19 -> 20 padded; one padding byte.
        data[12 + len(payload)] = 0x33
    assert decode_frame(bytes(data).ljust(FRAME_MAX, b"\xff"))["kind"] == "Corrupt"


@pytest.mark.parametrize("state", [3, 255])
def test_invalid_stage_is_not_silently_promoted(state):
    with pytest.raises(ValueError, match="stage"):
        decode_otm1(otm1(stage=state))


def test_frame_valid_but_invalid_payload_fails_closed():
    with pytest.raises(ValueError, match="invalid OTM1"):
        decode_ota_meta(pair(frame(b"not OTMA")))


def test_reject_trailing_otm1_data():
    with pytest.raises(ValueError, match="field lengths"):
        decode_otm1(otm1() + b"\x00")


def test_wrong_sector_size_is_not_a_valid_store():
    with pytest.raises(ValueError, match="two"):
        decode_ota_meta(b"\xff" * SECTOR)
