"""Physical, read-only OTA diagnostic qualification. No uploads or resets."""
import os
import pytest

from diagnostic import validate_diagnostic
from ota_http import OtaHttp

pytestmark = pytest.mark.bench


def test_runtime_matches_confirmed_boot_metadata(ota_campaign):
    origin = os.environ.get("OTA_HTTPS_ORIGIN")
    ca = os.environ.get("OTA_CA_FILE")
    token = os.environ.get("IOBEWI_OTA_TOKEN")
    expected_build = os.environ.get("OTA_EXPECTED_BUILD_ID")
    expected_mcu = os.environ.get("OTA_EXPECTED_CHIP")
    if not all((origin, ca, token, expected_build, expected_mcu)):
        pytest.skip("Explicit OTA TLS/identity variables required")
    board = ota_campaign.reserve()
    identity = board.identify()
    assert identity["chip"] == expected_mcu, "Bench and OTA MCU disagree"
    client = OtaHttp(origin, ca, token)
    status, body = client.diagnostic()
    assert status == 200, "Read-only diagnostic unavailable"
    result = validate_diagnostic(
        body, expected_build=expected_build, expected_mcu=expected_mcu
    )
    # Operator must additionally bind HTTPS origin to this exact physical MCU.
    # Matching chip is not sufficient proof of device association.
    ota_campaign.write("ota-runtime-diagnostic.json", {
        **result,
        "https_to_bench_identity_binding_verified": False,
    })
    assert result["running_slot"] in (0, 1)
