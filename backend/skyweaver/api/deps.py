from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from ..config import get_settings
from ..db import json_loads, session
from ..security import hash_api_key, read_token


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
            conn.execute("UPDATE api_keys SET last_used_at=datetime('now') WHERE id=?", (row["id"],))
            return {"type": "api_key", "id": row["id"], "username": row["name"], "scopes": json_loads(row["scopes"], [])}
    try:
        claims = read_token(token, settings.secret_key)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    return {"type": "user", "id": claims["sub"], "username": claims["username"], "scopes": claims.get("scopes", ["admin"]), "role": claims.get("role", "admin")}


def require_scope(scope: str):
    def _inner(principal: Annotated[dict, Depends(current_principal)]) -> dict:
        scopes = set(principal.get("scopes", []))
        if "admin" not in scopes and scope not in scopes:
            raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")
        return principal

    return _inner
