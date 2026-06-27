"""SQLAlchemy engine + session factory for the BenchLens PostgreSQL warehouse.

Reads connection settings from `config/settings.yaml` (with .env overrides).
Engine is lazy-built on first call so importing this module is side-effect free.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from benchlens.utils.config_loader import load_config


def _build_url(db_cfg: dict) -> str:
    return (
        f"postgresql+psycopg://{db_cfg['user']}:{db_cfg['password']}"
        f"@{db_cfg['host']}:{db_cfg['port']}/{db_cfg['name']}"
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a process-wide SQLAlchemy engine."""
    settings = load_config("settings")
    db_cfg = settings["database"]
    return create_engine(
        _build_url(db_cfg),
        pool_size=int(db_cfg.get("pool_size", 10)),
        max_overflow=int(db_cfg.get("max_overflow", 20)),
        pool_pre_ping=bool(db_cfg.get("pool_pre_ping", True)),
        echo=bool(db_cfg.get("echo", False)),
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return a process-wide session factory bound to the engine."""
    return sessionmaker(
        bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session: Session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """Quick connectivity check. Returns True if `SELECT 1` succeeds."""
    from sqlalchemy import text

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
