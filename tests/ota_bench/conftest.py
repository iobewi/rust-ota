"""OTA-specific pytest evidence. Reuse the generic bench client and Campaign."""
import hashlib
import os
from pathlib import Path

import pytest
from iobewi_bench.qualification import Campaign


@pytest.fixture
def ota_campaign(bench_client, bench_run_dir, request, pytestconfig):
    directory = bench_run_dir / hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16]
    revisions = {name: os.environ.get(name, "not recorded") for name in (
        "BENCH_CLIENT_REVISION", "BENCH_SERVER_REVISION",
        "BENCH_PAGE_REVISION", "BENCH_TRANSPORT",
    )}
    campaign = Campaign(
        bench_client, pytestconfig.getoption("--bench-device"),
        directory, request.node.path, request.node.nodeid, revisions=revisions,
    )
    support = Path(__file__).read_bytes()
    (directory / "conftest.py").write_bytes(support)
    campaign.write("ota-fixture-sha256.json", {
        "sha256": hashlib.sha256(support).hexdigest(),
    })
    # Campaign already preserves the executed recipe and generic bench client.
    # Record project-owned helper bytes too, not just names or mutable Git refs.
    helper_hashes = {}
    for name in (
        "boot_metadata.py", "boot_transitions.py",
        "ota_meta.py", "diagnostic.py", "ota_http.py",
        "refusal_assertions.py",
    ):
        source = Path(__file__).with_name(name).read_bytes()
        (directory / name).write_bytes(source)
        helper_hashes[name] = hashlib.sha256(source).hexdigest()
    campaign.write("ota-support-sha256.json", helper_hashes)
    request.node._ota_campaign = campaign
    try:
        campaign.start()  # Connected, unreserved, no quarantine/grant; event cursor.
        yield campaign
    finally:
        campaign.close()  # All reservations, bounded events, post-state, errors.


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    campaign = getattr(item, "_ota_campaign", None)
    if campaign is not None:
        campaign.client.record("assertions.jsonl", {
            "phase": report.when,
            "outcome": report.outcome,
            "exception_type": call.excinfo.typename if call.excinfo else None,
        })
