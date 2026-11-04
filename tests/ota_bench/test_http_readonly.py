"""Real OTA HTTPS smoke tests. Never upload/activate valid deployments.

The bench campaign provides device/epoch provenance and cleanup, but it does not
take ownership of the application's HTTPS socket. These tests do NOT prove OTA.
"""
import os

import pytest

from ota_http import OtaHttp

pytestmark = pytest.mark.bench


@pytest.fixture
def ota_endpoint():
    if not os.environ.get("OTA_HTTPS_ORIGIN") or not os.environ.get("OTA_CA_FILE"):
        pytest.skip("Set OTA_HTTPS_ORIGIN and OTA_CA_FILE for application HTTPS")
    token = os.environ.get("IOBEWI_OTA_TOKEN")
    if not token:
        pytest.skip("Set private IOBEWI_OTA_TOKEN for authenticated diagnostics")
    return OtaHttp(os.environ["OTA_HTTPS_ORIGIN"], os.environ["OTA_CA_FILE"], token)


def test_health_is_reachable_but_not_an_identity_proof(ota_campaign, ota_endpoint):
    # This does not flash, reset or reserve hardware. The bench snapshot tracks
    # the physical session to which this network observation is attributed.
    status, body = ota_endpoint.health()
    assert (status, body) == (200, b"ok")
    ota_campaign.write("ota-health.json", {
        "http_status": status, "body": body.decode("ascii"),
        "identity_verified": False, "slot_verified": False,
        "confirmation_verified": False,
    })

