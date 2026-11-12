"""Assertions for read-only, independent evidence of rejected OTA commands.

This is deliberately not a runner or scenario language. A refusal is a tuple
of exact HTTP status/body plus before/after durable flash evidence. A network
timeout is *indeterminate*, never evidence of refusal.
"""
from __future__ import annotations

import hashlib

from boot_metadata import decode_otadata
from ota_meta import decode_ota_meta
from ota_http import OtaTransportUncertain


def require_exact_refusal(reply: tuple[int, bytes], *, status: int, body: bytes) -> None:
    assert type(reply) is tuple and len(reply) == 2
    actual_status, actual_body = reply
    assert type(actual_status) is int and type(actual_body) is bytes
    assert actual_status == status, f"Unexpected HTTP response code {actual_status}"
    assert actual_body == body, "Unexpected HTTP refusal body"


def require_unchanged_persistent_state(
    before_otadata: bytes,
    after_otadata: bytes,
    before_ota_meta: bytes,
    after_ota_meta: bytes,
) -> dict:
    """No *persistent state change* across a rejected command.

    Validating both snapshots first prevents identical but corrupt flash from
    being mistaken for a successful security refusal. Does not establish the
    absence of transient writes or an authenticated image signature.
    """
    boots = [decode_otadata(value) for value in (before_otadata, after_otadata)]
    for records in boots:
        assert any(r["kind"] == "Ok" and r["state"] == "Valid" for r in records), (
            "Boot state lacks a confirmed fallback"
        )
    metas = [decode_ota_meta(value) for value in (before_ota_meta, after_ota_meta)]
    for state in metas:
        assert state["kind"] == "Payload", "OTA metadata unreadable/corrupt"
    assert before_otadata == after_otadata, "Rejected request changed boot selection"
    assert before_ota_meta == after_ota_meta, "Rejected request changed OTA transaction state"
    return {
        "otadata_sha256": hashlib.sha256(after_otadata).hexdigest(),
        "ota_meta_sha256": hashlib.sha256(after_ota_meta).hexdigest(),
        "durable_bytes_unchanged": True,
        "image_authenticated": False,
        "flash_write_count_proven_zero": False,
    }
