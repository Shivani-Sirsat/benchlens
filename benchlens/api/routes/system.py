"""System endpoints: health, version."""

from __future__ import annotations

from fastapi import APIRouter

from benchlens import __version__
from benchlens.api.schemas import HealthOut
from benchlens.utils.db import ping

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Liveness + DB readiness probe."""
    db_ok = ping()
    return HealthOut(
        status="ok" if db_ok else "degraded",
        db="up" if db_ok else "down",
        version=__version__,
    )


@router.get("/")
def root() -> dict[str, str]:
    """Tiny landing payload pointing at /docs."""
    return {
        "service": "BenchLens API",
        "version": __version__,
        "docs": "/docs",
    }
