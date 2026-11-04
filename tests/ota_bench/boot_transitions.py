"""Host-only assertions about durable BOOT v2 snapshots.

These checks cannot prove the execution of a candidate, firmware identity,
signature verification, or the OTM1 publication lifecycle.
"""
from boot_metadata import decode_otadata


def _entries(raw: bytes):
    return [item for item in decode_otadata(raw) if item["kind"] == "Ok"]


def _confirmed(entries, slot):
    found = [entry for entry in entries
             if entry["slot"] == slot and entry["state"] == "Valid"]
    assert len(found) == 1, f"Expected exactly one confirmed entry for slot {slot}"
    return found[0]


def require_confirmed_transition(before: bytes, after: bytes, *, from_slot: int, to_slot: int):
    """Require NEWER durable Valid selection without losing old Valid fallback."""
    assert (from_slot, to_slot) in ((0, 1), (1, 0))
    old = _entries(before)
    now = _entries(after)
    source = _confirmed(old, from_slot)
    fallback = _confirmed(now, from_slot)
    candidate = _confirmed(now, to_slot)
    assert fallback == source, "Confirmed fallback record changed unexpectedly"
    assert candidate["sequence"] > source["sequence"], "Candidate is not newer"
    assert not any(r["state"] in ("New", "PendingVerify") for r in now), (
        "Incomplete probation at final snapshot"
    )
    return {"source": source, "candidate": candidate, "fallback_preserved": True}


def require_rollback(before: bytes, after: bytes, *, fallback_slot: int):
    """Require confirmed baseline plus committed dead candidate in other slot."""
    assert fallback_slot in (0, 1)
    old = _entries(before)
    now = _entries(after)
    source = _confirmed(old, fallback_slot)
    fallback = _confirmed(now, fallback_slot)
    assert fallback == source, "Confirmed fallback metadata changed"
    others = [r for r in now if r["slot"] != fallback_slot]
    assert len(others) == 1, "No exact candidate metadata observation"
    candidate = others[0]
    assert candidate["sequence"] > source["sequence"]
    assert candidate["state"] in ("Invalid", "Aborted"), "Candidate not rejected"
    assert not any(r["state"] in ("New", "PendingVerify") for r in now)
    return {"fallback": fallback, "rejected": candidate}
