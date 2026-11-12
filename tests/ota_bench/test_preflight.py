"""Read-only preflight only: no OTA claims, no flash writes and no resets requested.

The loader used by identify/partitions may affect running firmware: coordinate
this read-only qualification with the browser operator.
"""
import os
import pytest

pytestmark = pytest.mark.bench


def test_bench_identity_and_target(ota_campaign):
    """Observe the connected hardware rather than inferring it from history."""
    board = ota_campaign.reserve()
    result = board.identify()
    assert isinstance(result, dict)
    assert result.get("chip") in {"esp32c3", "esp32s3"}, result.get("chip")
    ota_campaign.write("ota-preflight-identity.json", {
        "identified_chip": result["chip"],
        "expected_chip": os.getenv("OTA_EXPECTED_CHIP", "not configured"),
    })
    expected = os.getenv("OTA_EXPECTED_CHIP")
    if expected:
        assert result["chip"] == expected


def test_partition_geometry_explicit_opt_in(ota_campaign):
    """Never infer table address from an assumed board or from FF-filled flash."""
    address_hex = os.getenv("OTA_PARTITION_TABLE_OFFSET")
    if not address_hex:
        pytest.skip("Set OTA_PARTITION_TABLE_OFFSET after independent geometry review")
    address = int(address_hex, 0)
    assert address >= 0 and address % 4096 == 0
    board = ota_campaign.reserve()
    identity = board.identify()
    expected = os.getenv("OTA_EXPECTED_CHIP")
    if expected:
        assert identity["chip"] == expected
    partitions = board.partitions(address=address)
    assert isinstance(partitions, list) and partitions
    ota_campaign.write("ota-observed-partitions.json", {
        "table_offset": address, "partitions": partitions,
        "chip": identity["chip"],
    })
    # This proves that the bench parser returned a table, NOT that this is
    # the OTA project layout, that any slot is bootable, or that writing is safe.
