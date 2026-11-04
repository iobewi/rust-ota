"""Host-only adversarial HTTP transport tests; no network or MCU."""
import http.client
import pytest
from ota_http import OtaHttp, OtaProtocolError, OtaTransportUncertain


class Response:
    def __init__(self, status, data):
        self.status, self.data = status, data

    def read(self, n):
        assert n == 4097, "Response must be bounded"
        return self.data[:n]


class Connection:
    def __init__(self, *, status=200, data=b"ok", failure=None):
        self.status, self.data, self.failure = status, data, failure
        self.sent, self.closed = [], False

    def request(self, method, path, body=None, headers=None):
        self.sent.append((method, path, body, headers))
        if self.failure:
            raise self.failure

    def getresponse(self):
        return Response(self.status, self.data)

    def close(self):
        self.closed = True


def client_with(connection):
    client = object.__new__(OtaHttp)
    client._connection = lambda: connection
    return client


def test_no_retry_on_transport_timeout():
    connection = Connection(failure=TimeoutError("timeout"))
    client = client_with(connection)
    with pytest.raises(OtaTransportUncertain, match="TimeoutError"):
        client.request("POST", "/ota/activate")
    assert len(connection.sent) == 1, "Activation must not be submitted twice"
    assert connection.closed


def test_http_refusal_is_not_a_transport_failure():
    connection = Connection(status=409, data=b"activation refused")
    result = client_with(connection).request("POST", "/ota/activate")
    assert result == (409, b"activation refused")
    assert connection.closed


def test_oversized_response_is_rejected_and_connection_closed():
    connection = Connection(data=b"X" * 4097)
    with pytest.raises(OtaProtocolError, match="Oversized"):
        client_with(connection).request("GET", "/health")
    assert connection.closed


def test_other_routes_not_permitted():
    connection = Connection()
    with pytest.raises(OtaProtocolError, match="Unexpected"):
        client_with(connection).request("POST", "/arbitrary", body=b"x")
    assert connection.sent == []


def test_bounded_success_response():
    connection = Connection()
    assert client_with(connection).request("GET", "/health") == (200, b"ok")
    assert len(connection.sent) == 1
