"""Strict contract validation for the qualification-only OTA diagnostic endpoint."""
import json

STATE = {0: "New", 1: "PendingVerify", 2: "Valid", 3: "Invalid", 4: "Aborted"}


def validate_diagnostic(data: bytes, *, expected_build: str, expected_mcu: str):
    if not expected_build or not expected_mcu:
        raise ValueError("Expected build and MCU are mandatory")
    if len(data) > 4096:
        raise ValueError("Diagnostic response exceeds limit")
    diagnostic = json.loads(data)
    if not isinstance(diagnostic, dict):
        raise ValueError("Diagnostic root must be an object")
    if type(diagnostic.get("schema")) is not int or diagnostic["schema"] != 1:
        raise ValueError("Unknown diagnostic schema")
    if diagnostic.get("build_id") != expected_build:
        raise AssertionError("Unexpected firmware build")
    if diagnostic.get("mcu") != expected_mcu:
        raise AssertionError("Unexpected firmware target")
    slot = diagnostic.get("running_slot")
    if type(slot) is not int or slot not in (0, 1):
        raise ValueError("Invalid running slot")
    entries = diagnostic.get("boot_entries")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("Expected two BOOT metadata entries")
    normalized = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Invalid BOOT entry")
        kind = item.get("kind")
        if kind in ("Blank", "Corrupt"):
            if set(item) != {"kind"}:
                raise ValueError("Nonempty blank/corrupt entry")
            normalized.append({"kind": kind})
        elif kind == "Ok":
            seq, state = item.get("sequence"), item.get("state")
            if type(seq) is not int or not 0 < seq < 0xFFFFFFFF:
                raise ValueError("Invalid BOOT sequence")
            if type(state) is not int or state not in STATE:
                raise ValueError("Unknown BOOT state")
            if set(item) != {"kind", "sequence", "state"}:
                raise ValueError("Unknown BOOT record fields")
            normalized.append({
                "kind": "Ok", "sequence": seq, "state": STATE[state],
                "slot": (seq - 1) % 2,
            })
        else:
            raise ValueError("Unknown BOOT metadata kind")
    if diagnostic.get("otm1_observed") is not False:
        raise ValueError("OTM1 not observable in v1 diagnostic")
    if diagnostic.get("image_authenticated") is not False:
        raise ValueError("Image authenticity not established by diagnostics")
    if not any(r["kind"] == "Ok" and r["state"] == "Valid"
               and r["slot"] == slot for r in normalized):
        raise AssertionError("Running slot lacks confirmed BOOT metadata")
    return {
        "schema": 1, "build_id": expected_build, "mcu": expected_mcu,
        "running_slot": slot, "boot_entries": normalized,
        "otm1_observed": False, "image_authenticated": False,
    }
