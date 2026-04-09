from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.db.models import User


class AccessTokenError(ValueError):
    pass


SEED_ACCESS_NAMESPACE = uuid.UUID("b2b82b0b-1220-4285-bb45-f4a1ff4af5ec")


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    email: str
    expires_at: datetime


def _settings():
    return get_settings()


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def build_seed_access_code(email: str) -> str:
    settings = _settings()
    normalized = email.strip().lower()
    digest = uuid.uuid5(SEED_ACCESS_NAMESPACE, f"{settings.access_code_pepper}:{normalized}").hex
    return f"payfi-{digest[:6]}-{digest[6:12]}"


def hash_access_code(access_code: str) -> str:
    settings = _settings()
    normalized = access_code.strip()
    digest = hashlib.sha256(
        f"{settings.access_code_pepper}:{normalized}".encode("utf-8")
    ).hexdigest()
    return digest


def verify_access_code(access_code: str, access_code_hash: str) -> bool:
    candidate_hash = hash_access_code(access_code)
    return hmac.compare_digest(candidate_hash, access_code_hash)


def issue_access_token(user: User) -> tuple[str, datetime]:
    settings = _settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=max(settings.access_token_ttl_seconds, 300))
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "kind": "access_session",
    }
    encoded_payload = _b64url_encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        settings.access_token_secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}", expires_at


def parse_access_token(access_token: str) -> AccessTokenClaims:
    settings = _settings()
    try:
        payload_part, signature_part = access_token.strip().split(".", 1)
    except ValueError as exc:
        raise AccessTokenError("malformed access token") from exc

    expected_signature = hmac.new(
        settings.access_token_secret.encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual_signature = _b64url_decode(signature_part)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AccessTokenError("invalid access token signature")

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AccessTokenError("invalid access token payload") from exc

    if payload.get("kind") != "access_session":
        raise AccessTokenError("invalid access token kind")

    try:
        user_id = uuid.UUID(str(payload["sub"]))
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise AccessTokenError("invalid access token claims") from exc

    if expires_at <= datetime.now(timezone.utc):
        raise AccessTokenError("access token expired")

    return AccessTokenClaims(
        user_id=user_id,
        email=str(payload.get("email") or ""),
        expires_at=expires_at,
    )
