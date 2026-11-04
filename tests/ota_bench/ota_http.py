"""Bounded OTA HTTP protocol adapter; application HTTPS is NOT a bench serial transport.

No hidden retries. A lost activation response has an unknown outcome.
All credentials are supplied through process environment, never logged or persisted.
"""
from __future__ import annotations

import hashlib
import http.client
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit


class OtaProtocolError(RuntimeError):
    """Invalid local configuration/protocol response, not a device refusal."""


class OtaTransportUncertain(RuntimeError):
    """Network failure; the remote operation may have been accepted."""


class OtaHttp:
    def __init__(self, origin: str, ca_file: str, token: str, *, timeout: float = 15):
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

    def request(self, method: str, path: str, *, headers=None, body=b""):
        if method not in ("GET", "POST") or path not in (
            "/health", "/ota/upload", "/ota/activate"
        ):
            raise OtaProtocolError("Unexpected OTA operation")
        conn = self._connection()
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            status = response.status
            data = response.read(4097)
            if len(data) > 4096:
                raise OtaProtocolError("Oversized response")
            return status, data
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            # Never automatically replay a POST when submission may have succeeded.
            raise OtaTransportUncertain(type(error).__name__) from None
        finally:
            conn.close()

    def health(self):
        return self.request("GET", "/health")

    @staticmethod
    def validate_id(deployment_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", deployment_id, flags=re.ASCII):
            raise ValueError("Invalid deployment id")

    @staticmethod
    def validate_manifest(manifest: str | None):
        if manifest is None:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_-]+", manifest, flags=re.ASCII):
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

    def upload(self, image: Path, deployment_id: str, *, manifest=None):
        """One attempt, bounded in-memory image; prohibit use for large firmware.

        The hardware campaign must use a chunked sender before full-size uploads.
        """
        self.validate_id(deployment_id)
        manifest = self.validate_manifest(manifest)
        data = Path(image).read_bytes()
        if not data or len(data) > 2 * 1024 * 1024:
            raise ValueError("Image length exceeds prototype limit")
        headers = {
            "Authorization": "Bearer " + self.token,
            "X-Deployment-ID": deployment_id,
            "X-Image-SHA256": "sha256:" + hashlib.sha256(data).hexdigest(),
            "Content-Length": str(len(data)),
        }
        if manifest is not None:
            headers["X-Image-Manifest"] = manifest
        return self.request("POST", "/ota/upload", headers=headers, body=data)
