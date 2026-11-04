"""Offline admission guards for separately approved activation."""
import hashlib
import json

import pytest
from test_activation import approved_activation


def run_fixture():
    return approved_activation.__wrapped__()


def test_activation_without_approval_skips(monkeypatch):
    monkeypatch.delenv("OTA_APPROVED_ACTIVATION", raising=False)
    with pytest.raises(pytest.skip.Exception):
        run_fixture()


def test_activation_requires_exact_plan_digest(monkeypatch):
    monkeypatch.setenv("OTA_APPROVED_ACTIVATION", "yes")
    monkeypatch.delenv("OTA_ACTIVATION_PLAN", raising=False)
    monkeypatch.delenv("OTA_ACTIVATION_PLAN_SHA256", raising=False)
    with pytest.raises(pytest.fail.Exception, match="activation plan"):
        run_fixture()


def test_stage_only_plan_cannot_authorize_activation(monkeypatch, tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({
        "schema": 1, "scope": "ota.stage-and-readback",
    }))
    monkeypatch.setenv("OTA_APPROVED_ACTIVATION", "yes")
    monkeypatch.setenv("OTA_ACTIVATION_PLAN", str(path))
    monkeypatch.setenv("OTA_ACTIVATION_PLAN_SHA256",
                       hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(AssertionError, match="Incomplete"):
        run_fixture()
