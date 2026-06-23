import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def make_token(payload: dict[str, Any], secret_key: str, minutes: int = 1440) -> str:
    now = datetime.now(UTC)
    data = {**payload, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(data, secret_key, algorithm="HS256")


def read_token(token: str, secret_key: str) -> dict[str, Any]:
    return jwt.decode(token, secret_key, algorithms=["HS256"])


def create_api_key() -> tuple[str, str, str]:
    raw = "swh_" + secrets.token_urlsafe(32)
    return raw, raw[:12], hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_api_key(raw: str, hashed: str) -> bool:
    return secrets.compare_digest(hash_api_key(raw), hashed)
