"""Host-only tests: no bench, no hardware, no TLS traffic."""
from pathlib import Path
import pytest
from ota_http import OtaHttp, OtaProtocolError, OtaTransportUncertain


class StubHttp(OtaHttp):
    def __init__(self, reply=(200, b"ok")):
        self.reply = reply
        self.calls = []
        self.token = "unit-test-token"

    def request(self, method, path, *, headers=None, body=b""):
        self.calls.append((method, path, headers or {}, body))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.mark.parametrize("name", ["", "bad/id", "a" * 65, "x\r\nheader", "a b"])
def test_invalid_deployment_id_fails_before_network(name):
    client = StubHttp()
    with pytest.raises(ValueError, match="deployment id"):
        client.activate(name)
    assert client.calls == []


@pytest.mark.parametrize("manifest", ["=", "ab+", "ab/", "x\n", ""])
def test_invalid_manifest_fails_before_network(manifest):
    client = StubHttp()
    with pytest.raises(ValueError, match="base64url"):
        client.activate("candidate-01", manifest=manifest)
    assert client.calls == []


def test_activation_has_zero_body_and_replays_exact_manifest():
    client = StubHttp((200, b"activating"))
    assert client.activate("candidate-01", manifest="YWJj") == (200, b"activating")
    method, path, headers, body = client.calls[0]
    assert (method, path, body) == ("POST", "/ota/activate", b"")
    assert headers["X-Deployment-ID"] == "candidate-01"
    assert headers["X-Image-Manifest"] == "YWJj"
    assert headers["Authorization"] == "Bearer unit-test-token"


def test_unauthorized_activation_omits_bearer():
    client = StubHttp((401, b""))
    assert client.activate("not-a-deployment", authorized=False)[0] == 401
    assert "Authorization" not in client.calls[0][2]


def test_upload_digest_body_and_headers(tmp_path):
    image = tmp_path / "candidate.bin"
    image.write_bytes(b"test-image" * 32)
    client = StubHttp((200, b"staged"))
    assert client.upload(image, "upload-01", manifest="YWJj") == (200, b"staged")
    _, path, headers, body = client.calls[0]
    import hashlib
    assert path == "/ota/upload"
    assert headers["Content-Length"] == str(len(body))
    assert headers["X-Image-SHA256"] == "sha256:" + hashlib.sha256(body).hexdigest()
    assert headers["X-Image-Manifest"] == "YWJj"
    assert body == image.read_bytes()


def test_empty_upload_rejected_locally_without_network(tmp_path):
    image = tmp_path / "empty.bin"
    image.write_bytes(b"")
    client = StubHttp()
    with pytest.raises(ValueError, match="length"):
        client.upload(image, "upload-01")
    assert client.calls == []


def test_transport_uncertainty_is_not_a_device_refusal():
    client = StubHttp(OtaTransportUncertain("TimeoutError"))
    with pytest.raises(OtaTransportUncertain, match="TimeoutError"):
        client.activate("candidate-01")
    assert len(client.calls) == 1
