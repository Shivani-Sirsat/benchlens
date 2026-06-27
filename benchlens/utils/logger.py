"""Centralized logger configuration loader.

Reads `config/logging.yaml` and applies it via `logging.config.dictConfig`.
Falls back to a sensible basic config if the file is missing.
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml

_CONFIGURED = False
_LOG_DIR = Path("logs")
_CONFIG_PATH = Path("config") / "logging.yaml"


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(config_path: Path | str = _CONFIG_PATH) -> None:
    """Configure the root logging system from YAML. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    _ensure_log_dir()
    path = Path(config_path)

    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logging.getLogger(__name__).warning("Logging config %s not found; using basicConfig.", path)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Call this from any module."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
