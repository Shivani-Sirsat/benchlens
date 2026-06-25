"""FastAPI application factory for the BenchLens REST API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from benchlens import __version__
from benchlens.api import deps
from benchlens.utils.config_loader import load_config
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


def _cors_origins() -> list[str]:
    cfg = load_config("settings")
    return list((cfg.get("api") or {}).get("cors_origins") or [])


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """One-shot startup: init auth singletons + log a startup line."""
    deps.init_auth_state()
    log.info("BenchLens API v%s starting up.", __version__)
    yield
    log.info("BenchLens API shutting down.")


def create_app() -> FastAPI:
    """Build the FastAPI app. Routers are attached here."""
    app = FastAPI(
        title="BenchLens API",
        description="REST API for BenchLens — benchmark analytics, "
        "regression detection, ETL audit.",
        version=__version__,
        lifespan=_lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins() or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routers (imported here to avoid premature DB engine init) -----
    from benchlens.api.routes import auth, dims, etl, quality, runs, system

    app.include_router(system.router, tags=["system"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(runs.router, prefix="/runs", tags=["runs"])
    app.include_router(dims.router, tags=["dimensions"])
    app.include_router(quality.router, prefix="/quality", tags=["quality"])
    app.include_router(etl.router, prefix="/etl", tags=["etl"])

    # ---- JSON error handler so unhandled errors produce a clean body ----
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        log.exception("Unhandled API error")
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"},
        )

    return app


# Module-level instance for `uvicorn benchlens.api.app:app`.
app: FastAPI = create_app()


def jsonable(obj: Any) -> Any:  # noqa: D401 — re-export
    """Convenience wrapper used by routes when constructing manual responses."""
    return jsonable_encoder(obj)
