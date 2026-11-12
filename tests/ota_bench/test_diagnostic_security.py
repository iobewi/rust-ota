"""Read-only physical rejection: an unauthenticated diagnostic request is 401.

This proves only an HTTP access-control response plus unchanged *observed*
runtime BOOT entries. It does not prove zero flash writes or OTM1 integrity.
"""
import os

import pytest

from diagnostic import validate_diagnostic
from ota_http import OtaHttp

pytestmark = pytest.mark.bench


def test_unauthenticated_ota_diagnostic_refused(ota_campaign):
    origin = os.environ.get("OTA_HTTPS_ORIGIN")
    ca = os.environ.get("OTA_CA_FILE")
    token = os.environ.get("IOBEWI_OTA_TOKEN")
    build = os.environ.get("OTA_EXPECTED_BUILD_ID")
    target = os.environ.get("OTA_EXPECTED_CHIP")
    if not all((origin, ca, token, build, target)):
        pytest.skip("HTTPS TLS credentials and expected build/chip required")

    board = ota_campaign.reserve()
    identity = board.identify()
    assert identity["chip"] == target, "Unexpected board MCU"
    app = OtaHttp(origin, ca, token)
    before_status, before_body = app.diagnostic()
    assert before_status == 200, "Authenticated diagnostic unavailable"
    before = validate_diagnostic(
        before_body, expected_build=build, expected_mcu=target,
        expected_mac=identity["mac"],
    )

    # No Authorization header at all. The firmware's read-only handler must
    # reject before acquiring the SystemBoot flash snapshot.
    status, response = app.request("GET", "/ota/diagnostic", headers={})
    assert (status, response) == (401, b"unauthorized"), (
        f"Expected HTTP 401, got HTTP {status}"
    )
    after_status, after_body = app.diagnostic()
    assert after_status == 200, "Diagnostic lost after refusal"
    after = validate_diagnostic(
        after_body, expected_build=build, expected_mcu=target,
        expected_mac=identity["mac"],
    )
    assert after == before, "Refusal changed observed runtime BOOT state"
    ota_campaign.write("diagnostic-auth-refusal.json", {
        "refusal_status": status,
        "target_mac": before["station_mac"],
        "build_id": build,
        "runtime_boot_unchanged": True,
        "durable_otm1_unchanged_verified": False,
        "zero_flash_writes_proven": False,
    })
