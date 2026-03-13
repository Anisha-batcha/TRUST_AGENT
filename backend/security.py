from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


def utc_now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def hash_password(password: str, salt: str | None = None) -> str:
    salt_bytes = (salt or secrets.token_hex(16)).encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 120_000)
    return f"{salt_bytes.decode('utf-8')}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    check = hash_password(password, salt=salt)
    return hmac.compare_digest(check, f"{salt}${digest_hex}")


class JWTManager:
    def __init__(self, secret: str | None = None, algorithm: str = "HS256") -> None:
        self.secret = (secret or os.getenv("JWT_SECRET") or "trustagent-dev-secret").encode("utf-8")
        self.algorithm = algorithm

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    @staticmethod
    def _b64url_decode(data: str) -> bytes:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))

    def create_token(self, subject: str, expires_hours: int = 12, extra: dict[str, Any] | None = None) -> str:
        header = {"alg": self.algorithm, "typ": "JWT"}
        now = utc_now_ts()
        payload = {
            "sub": subject,
            "iat": now,
            "nbf": now,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=expires_hours)).timestamp()),
        }
        if extra:
            payload.update(extra)

        header_b64 = self._b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = self._b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        sig = hmac.new(self.secret, signing_input, hashlib.sha256).digest()
        return f"{header_b64}.{payload_b64}.{self._b64url(sig)}"

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            header_b64, payload_b64, sig_b64 = token.split(".", 2)
        except ValueError as exc:
            raise ValueError("Invalid token format") from exc

        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(self.secret, signing_input, hashlib.sha256).digest()
        actual_sig = self._b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid token signature")

        payload = json.loads(self._b64url_decode(payload_b64).decode("utf-8"))
        now = utc_now_ts()
        if int(payload.get("nbf", now)) > now:
            raise ValueError("Token not active yet")
        if int(payload.get("exp", 0)) < now:
            raise ValueError("Token expired")
        return payload


jwt_manager = JWTManager()
