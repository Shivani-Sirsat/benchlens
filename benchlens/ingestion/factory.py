"""Factory for building connectors from configuration."""

from __future__ import annotations

from typing import Any

from benchlens.ingestion.base_connector import BaseConnector, ConnectorError
from benchlens.ingestion.csv_connector import CSVConnector
from benchlens.ingestion.json_connector import JSONConnector
from benchlens.ingestion.rest_connector import RESTConnector
from benchlens.ingestion.sql_connector import SQLConnector

_REGISTRY: dict[str, type[BaseConnector]] = {
    CSVConnector.kind: CSVConnector,
    JSONConnector.kind: JSONConnector,
    RESTConnector.kind: RESTConnector,
    SQLConnector.kind: SQLConnector,
}


def register_connector(cls: type[BaseConnector]) -> type[BaseConnector]:
    """Decorator for custom connectors."""
    if not cls.kind:
        raise ValueError(f"{cls.__name__} must set a non-empty 'kind' attribute.")
    _REGISTRY[cls.kind] = cls
    return cls


def available_kinds() -> list[str]:
    return sorted(_REGISTRY.keys())


def build_connector(name: str, config: dict[str, Any]) -> BaseConnector:
    """Instantiate the connector indicated by `config['connector']`."""
    kind = (config or {}).get("connector")
    if not kind:
        raise ConnectorError(f"Source {name!r} is missing the 'connector' field.")
    if kind not in _REGISTRY:
        raise ConnectorError(
            f"Source {name!r} uses unknown connector {kind!r}. "
            f"Available: {available_kinds()}"
        )
    cls = _REGISTRY[kind]
    return cls(name=name, config=config)


def load_source_config(source_name: str) -> dict[str, Any]:
    """Look up a source by name in config/sources.yaml."""
    from benchlens.utils.config_loader import load_config

    cfg = load_config("sources") or {}
    sources = cfg.get("sources") or []
    for entry in sources:
        if entry.get("name") == source_name:
            return entry
    raise ConnectorError(
        f"Source {source_name!r} not found in config/sources.yaml. "
        f"Available: {[s.get('name') for s in sources]}"
    )


def build_connector_by_name(source_name: str) -> BaseConnector:
    """One-shot helper: read sources.yaml, build the connector."""
    return build_connector(source_name, load_source_config(source_name))
