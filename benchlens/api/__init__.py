"""BenchLens REST API (FastAPI + JWT + RBAC). Implemented on Day 6."""

from benchlens.api.app import app, create_app

__all__ = ["app", "create_app"]
