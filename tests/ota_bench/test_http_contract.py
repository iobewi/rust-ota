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


class StreamingConnection:
    def __init__(self):
        self.headers = {}
        self.sent = []
        self.closed = False
        self.path = None

    def putrequest(self, method, path):
        assert method == "POST"
        self.path = path

    def putheader(self, name, value):
        self.headers[name] = value

    def endheaders(self):
        pass

    def send(self, chunk):
        self.sent.append(chunk)

    def getresponse(self):
        class Response:
            status = 200

            def read(self, limit):
                assert limit == 4097
                return b"staged"

        return Response()

    def close(self):
        self.closed = True


def test_streamed_upload_digest_and_body(tmp_path):
    image = tmp_path / "candidate.bin"
    image.write_bytes(b"test-image" * 1024)
    expected = __import__("hashlib").sha256(image.read_bytes()).hexdigest()
    client = StubHttp()
    connection = StreamingConnection()
    client._connection = lambda: connection
    assert client.upload(image, "upload-01", manifest="YWJj",
                         expected_sha256=expected, max_bytes=20480) == (200, b"staged")
    assert connection.path == "/ota/upload"
    assert connection.headers["Content-Length"] == str(image.stat().st_size)
    assert connection.headers["X-Image-SHA256"] == "sha256:" + expected
    assert connection.headers["X-Image-Manifest"] == "YWJj"
    assert b"".join(connection.sent) == image.read_bytes()
    assert max(map(len, connection.sent)) <= 2048
    assert connection.closed


def test_empty_upload_rejected_locally_without_network(tmp_path):
    image = tmp_path / "empty.bin"
    image.write_bytes(b"")
    client = StubHttp()
    with pytest.raises(ValueError, match="Image size"):
        client.upload(image, "upload-01", expected_sha256="0" * 64,
                      max_bytes=4096)
    assert client.calls == []


def test_upload_wrong_digest_refused_before_connection(tmp_path):
    image = tmp_path / "candidate.bin"
    image.write_bytes(b"payload")
    client = StubHttp()
    with pytest.raises(ValueError, match="SHA-256 differs"):
        client.upload(image, "upload-01", expected_sha256="0" * 64,
                      max_bytes=4096)
    assert client.calls == []


def test_upload_capacity_must_be_approved(tmp_path):
    image = tmp_path / "candidate.bin"
    image.write_bytes(b"payload")
    digest = __import__("hashlib").sha256(image.read_bytes()).hexdigest()
    client = StubHttp()
    with pytest.raises(ValueError, match="capacity"):
        client.upload(image, "upload-01", expected_sha256=digest, max_bytes=3)
    assert client.calls == []


def test_transport_uncertainty_is_not_a_device_refusal():
    client = StubHttp(OtaTransportUncertain("TimeoutError"))
    with pytest.raises(OtaTransportUncertain, match="TimeoutError"):
        client.activate("candidate-01")
    assert len(client.calls) == 1
