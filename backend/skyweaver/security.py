import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt


MAX_BCRYPT_PASSWORD_BYTES = 72


def _password_bytes(password: str) -> bytes:
    data = password.encode("utf-8")
    if len(data) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password must be 72 bytes or fewer for bcrypt")
    return data


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    data = password.encode("utf-8")
    if len(data) > MAX_BCRYPT_PASSWORD_BYTES:
        data = data[:MAX_BCRYPT_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(data, password_hash.encode("utf-8"))
    except ValueError:
        return False


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
