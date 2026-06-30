import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings
from .db import json_dumps, json_loads

SECRET_ENVELOPE = "fernet.v1"


def fernet_key() -> bytes:
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_config_envelope(config: dict[str, Any]) -> dict[str, str]:
    token = Fernet(fernet_key()).encrypt(json_dumps(config).encode("utf-8")).decode("ascii")
    return {"_skyweaver_secret": SECRET_ENVELOPE, "token": token}


def decrypt_config_envelope(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json_loads(value, {})
    if not isinstance(value, dict):
        return {}
    if value.get("_skyweaver_secret") != SECRET_ENVELOPE:
        return value
    token = value.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("Encrypted remote target config is missing a token")
    try:
        plaintext = Fernet(fernet_key()).decrypt(token.encode("ascii"))
    except InvalidToken as exc:
        raise ValueError("Encrypted remote target config cannot be decrypted with the current secret key") from exc
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Encrypted remote target config payload is invalid") from exc
    return decoded if isinstance(decoded, dict) else {}


def is_encrypted_config(value: Any) -> bool:
    if isinstance(value, str):
        value = json_loads(value, {})
    return isinstance(value, dict) and value.get("_skyweaver_secret") == SECRET_ENVELOPE
