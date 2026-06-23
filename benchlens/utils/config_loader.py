"""YAML configuration loader with environment variable interpolation.

Supports `${VAR}` and `${VAR:-default}` syntax inside YAML strings,
so the same file works for local dev and containerized runs.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env once on import so ${VAR} resolution works in local dev.
load_dotenv(override=False)

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")
_CONFIG_DIR = Path("config")


def _interpolate(value: Any) -> Any:
    """Replace ${VAR} / ${VAR:-default} occurrences in strings using os.environ."""
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            var_name, default = match.group(1), match.group(2)
            return os.environ.get(var_name, default if default is not None else "")
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


@lru_cache(maxsize=None)
def load_config(name: str = "settings", config_dir: Path | str = _CONFIG_DIR) -> dict[str, Any]:
    """Load a YAML config file from `config/<name>.yaml`. Cached per name."""
    path = Path(config_dir) / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return _interpolate(raw)


def reload_configs() -> None:
    """Clear the cache so subsequent loads re-read from disk."""
    load_config.cache_clear()
