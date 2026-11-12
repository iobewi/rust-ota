"""Bounded OTA HTTP adapter: application HTTPS, never a second serial transport.

No implicit retry. An HTTP transport failure after sending a POST has an
uncertain hardware outcome. Credentials never enter exceptions or report files.
"""
from __future__ import annotations

import hashlib
import http.client
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit


class OtaProtocolError(RuntimeError):
    """Invalid local protocol or unexpected response framing."""


class OtaTransportUncertain(RuntimeError):
    """Remote side may have received a mutation; do not automatically replay."""


class OtaHttp:
    def __init__(self, origin: str, ca_file: str, token: str, *, timeout: float = 60):
        url = urlsplit(origin)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("OTA origin must be an HTTPS origin without credentials/path")
        if not token or "\r" in token or "\n" in token:
            raise ValueError("A nonempty OTA token is required")
        if timeout <= 0 or timeout > 120:
            raise ValueError("Invalid timeout")
        self.host, self.port = url.hostname, url.port or 443
        self.token, self.timeout = token, timeout
        self.context = ssl.create_default_context(cafile=ca_file)

    def _connection(self):
        return http.client.HTTPSConnection(
            self.host, self.port, context=self.context, timeout=self.timeout
        )

    @staticmethod
    def _response(connection):
        response = connection.getresponse()
        status = response.status
        data = response.read(4097)
        if len(data) > 4096:
            raise OtaProtocolError("Oversized response")
        return status, data

    def request(self, method: str, path: str, *, headers=None, body=b""):
        if method not in ("GET", "POST") or path not in (
            "/health", "/ota/upload", "/ota/activate", "/ota/diagnostic"
        ):
            raise OtaProtocolError("Unexpected OTA operation")
        conn = self._connection()
        try:
            conn.request(method, path, body=body, headers=headers or {})
            return self._response(conn)
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            raise OtaTransportUncertain(type(error).__name__) from None
        finally:
            conn.close()

    def health(self):
        return self.request("GET", "/health")

    def diagnostic(self):
        return self.request(
            "GET", "/ota/diagnostic",
            headers={"Authorization": "Bearer " + self.token},
        )

    @staticmethod
    def validate_id(deployment_id: str):
        if not isinstance(deployment_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,64}", deployment_id, flags=re.ASCII
        ):
            raise ValueError("Invalid deployment id")

    @staticmethod
    def validate_manifest(manifest: str | None):
        if manifest is None:
            return None
        if not isinstance(manifest, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", manifest, flags=re.ASCII
        ):
            raise ValueError("Invalid unpadded base64url IAM1 envelope")
        return manifest

    def activate(self, deployment_id: str, *, manifest=None, authorized=True):
        self.validate_id(deployment_id)
        manifest = self.validate_manifest(manifest)
        headers = {"X-Deployment-ID": deployment_id}
        if authorized:
            headers["Authorization"] = "Bearer " + self.token
        if manifest is not None:
            headers["X-Image-Manifest"] = manifest
        return self.request("POST", "/ota/activate", headers=headers)

    def upload(self, image: Path, deployment_id: str, *, manifest=None,
               expected_sha256: str, max_bytes: int):
        """Single streaming attempt, no retries, no complete image RAM allocation.

        Require an independently approved digest and geometry-derived size bound.
        The server still validates the digest and image format; 200 staged does
        not establish that the new firmware has booted.
        """
        self.validate_id(deployment_id)
        manifest = self.validate_manifest(manifest)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256, flags=re.ASCII):
            raise ValueError("Expected SHA-256 must be lowercase 64-digit hex")
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
            raise ValueError("An explicit positive slot capacity is required")
        image = Path(image)
        with image.open("rb") as source:
            length = image.stat().st_size
            if not 0 < length <= max_bytes:
                raise ValueError("Image size exceeds approved slot capacity")
            digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != expected_sha256:
                raise ValueError("Candidate changed or expected SHA-256 differs")
            source.seek(0)
            headers = {
                "Authorization": "Bearer " + self.token,
                "X-Deployment-ID": deployment_id,
                "X-Image-SHA256": "sha256:" + digest,
                "Content-Length": str(length),
            }
            if manifest is not None:
                headers["X-Image-Manifest"] = manifest
            conn = self._connection()
            try:
                conn.putrequest("POST", "/ota/upload")
                for key, value in headers.items():
                    conn.putheader(key, value)
                conn.endheaders()
                remaining = length
                sent_hash = hashlib.sha256()
                while remaining:
                    chunk = source.read(min(2048, remaining))
                    if not chunk:
                        raise OtaTransportUncertain("Source shortened while streaming")
                    conn.send(chunk)
                    sent_hash.update(chunk)
                    remaining -= len(chunk)
                if sent_hash.hexdigest() != digest:
                    raise OtaTransportUncertain("Source changed while streaming")
                return self._response(conn)
            except (OSError, TimeoutError, http.client.HTTPException) as error:
                raise OtaTransportUncertain(type(error).__name__) from None
            finally:
                conn.close()
