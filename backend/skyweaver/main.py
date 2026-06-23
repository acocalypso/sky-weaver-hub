from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.responses import http_exception_handler, unhandled_exception_handler
from .api.routes import router
from .config import get_settings
from .db import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(title="Sky Weaver Hub API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    app.include_router(router)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    static_dir = settings.data_dir / "web"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


app = create_app()
