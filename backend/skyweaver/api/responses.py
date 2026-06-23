from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


def meta(request_id: str | None = None) -> dict[str, str]:
    return {"request_id": request_id or str(uuid4()), "timestamp": datetime.now(UTC).isoformat()}


def ok(data: Any, request_id: str | None = None, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"data": data, "meta": meta(request_id)}
    if extra_meta:
        payload["meta"].update(extra_meta)
    return payload


def error_response(code: str, message: str, status_code: int = 400, details: dict[str, Any] | None = None, request_id: str | None = None) -> JSONResponse:
    rid = request_id or str(uuid4())
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}, "request_id": rid}},
    )


async def http_exception_handler(request: Request, exc):
    return error_response("HTTP_ERROR", str(exc.detail), exc.status_code, request_id=getattr(request.state, "request_id", None))


async def unhandled_exception_handler(request: Request, exc):
    return error_response("INTERNAL_ERROR", "Unexpected server error.", 500, {"type": exc.__class__.__name__}, getattr(request.state, "request_id", None))
