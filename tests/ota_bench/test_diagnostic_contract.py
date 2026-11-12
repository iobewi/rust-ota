"""No device: negative coverage of the qualification diagnostic contract."""
import json
import pytest
from diagnostic import validate_diagnostic


def sample():
    return {
        "schema": 2, "build_id": "ota-A-001", "mcu": "esp32c3",
        "station_mac": "02:01:23:45:67:89",
        "running_slot": 0,
        "boot_entries": [
            {"kind": "Ok", "sequence": 1, "state": 2},
            {"kind": "Blank"},
        ],
        "otm1_observed": False, "image_authenticated": False,
    }


def validate(payload):
    return validate_diagnostic(json.dumps(payload).encode(),
                               expected_build="ota-A-001", expected_mcu="esp32c3",
                               expected_mac="02:01:23:45:67:89")


def test_valid_diagnostic_maps_runtime_to_valid_entry():
    result = validate(sample())
    assert result["running_slot"] == 0
    assert result["boot_entries"][0]["state"] == "Valid"
    assert result["otm1_observed"] is False


@pytest.mark.parametrize("key,wrong", [
    ("schema", 1), ("build_id", "ota-B-002"), ("mcu", "esp32s3"), ("station_mac", "11:22:33:44:55:66"),
    ("running_slot", 1), ("running_slot", "0"),
    ("otm1_observed", True), ("image_authenticated", True),
])
def test_wrong_identity_or_unproved_claims_fail(key, wrong):
    payload = sample()
    payload[key] = wrong
    with pytest.raises((AssertionError, ValueError)):
        validate(payload)


@pytest.mark.parametrize("entry", [
    {"kind": "Unknown"}, {"kind": "Ok", "sequence": 1, "state": 8},
    {"kind": "Ok", "sequence": 0, "state": 2},
    {"kind": "Ok", "sequence": 1, "state": 1},
    {"kind": "Ok", "sequence": 1, "state": 2, "extra": "ignored"},
    {"kind": "Blank", "state": 2},
])
def test_malformed_or_unconfirmed_metadata_is_not_pass(entry):
    payload = sample()
    payload["boot_entries"][0] = entry
    with pytest.raises((AssertionError, ValueError)):
        validate(payload)


def test_invalid_json_is_not_silently_accepted():
    with pytest.raises(json.JSONDecodeError):
        validate_diagnostic(b"{", expected_build="ota-A-001", expected_mcu="esp32c3",
                            expected_mac="02:01:23:45:67:89")


def test_missing_expected_build_is_not_an_opt_out():
    with pytest.raises(ValueError, match="mandatory"):
        validate_diagnostic(json.dumps(sample()).encode(),
                            expected_build="", expected_mcu="esp32c3",
                            expected_mac="02:01:23:45:67:89")
