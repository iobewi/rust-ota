"""Read-only physical observation of BOOT v2 otadata, opt-in.

A valid record is not proof of booted application or authenticated firmware.
"""
import hashlib
import json
import os

import pytest
from boot_metadata import SECTOR, decode_otadata

pytestmark = pytest.mark.bench


def test_otadata_v2_snapshot(ota_campaign):
    address = os.environ.get("OTA_OTADATA_OFFSET")
    if not address:
        pytest.skip("Explicit OTA_OTADATA_OFFSET required after partition map verification")
    if os.environ.get("OTA_READ_BOOT_METADATA") != "yes":
        pytest.skip("Set OTA_READ_BOOT_METADATA=yes for explicit bootloader flash observation")
    offset = int(address, 0)
    assert offset >= 0 and offset % SECTOR == 0
    board = ota_campaign.reserve()
    identity = board.identify()
    assert identity["chip"] in ("esp32c3", "esp32s3")
    size = identity.get("flash_size")
    assert type(size) is int and offset + 2 * SECTOR <= size
    raw = board.read_flash(address=offset, size=2 * SECTOR)
    records = decode_otadata(raw)
    ota_campaign.write("otadata-v2.json", {
        "offset": offset, "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "entries": records,
        "running_slot_observed": False,
        "boot_authenticated": False,
        "otm1_verified": False,
    })
    assert all(record["kind"] in ("Blank", "Corrupt", "Ok") for record in records)
    # A legacy, corrupted or empty region is a real observation, not a passing
    # v2 boot acceptance check; require at least one exact v2 entry.
    assert any(record["kind"] == "Ok" for record in records), (
        "No valid BOOT v2 metadata entry"
    )
