from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from ..config import get_settings
from ..db import json_loads, now_iso, session
from ..security import hash_api_key, parse_expiration, read_token, scopes_for_role


def current_principal(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Use Authorization: Bearer <token>")

    settings = get_settings()
    if token.startswith("swh_"):
        hashed = hash_api_key(token)
        with session() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE key_hash=? AND enabled=1", (hashed,)).fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Invalid API key")
            if row["expires_at"]:
                try:
                    expired = parse_expiration(row["expires_at"]) <= datetime.now(UTC)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=401, detail="Invalid API key expiration") from None
                if expired:
                    raise HTTPException(status_code=401, detail="API key has expired")
            conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (now_iso(), row["id"]))
            return {"type": "api_key", "id": row["id"], "username": row["name"], "scopes": json_loads(row["scopes"], [])}
    try:
        claims = read_token(token, settings.secret_key)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    with session() as conn:
        user = conn.execute("SELECT id, username, role FROM users WHERE id=?", (claims["sub"],)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {"type": "user", "id": user["id"], "username": user["username"], "scopes": scopes_for_role(user["role"]), "role": user["role"]}


def require_scope(scope: str):
    def _inner(principal: Annotated[dict, Depends(current_principal)]) -> dict:
        scopes = set(principal.get("scopes", []))
        if "admin" not in scopes and scope not in scopes:
            raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")
        return principal

    return _inner
