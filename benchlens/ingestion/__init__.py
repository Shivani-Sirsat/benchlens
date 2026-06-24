"""Ingestion connectors (CSV / JSON / REST / SQL)."""

from benchlens.ingestion.base_connector import BaseConnector, ConnectorError, IngestResult
from benchlens.ingestion.csv_connector import CSVConnector
from benchlens.ingestion.factory import (
    available_kinds,
    build_connector,
    build_connector_by_name,
    load_source_config,
    register_connector,
)
from benchlens.ingestion.json_connector import JSONConnector
from benchlens.ingestion.rest_connector import RESTConnector
from benchlens.ingestion.sql_connector import SQLConnector

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "IngestResult",
    "CSVConnector",
    "JSONConnector",
    "RESTConnector",
    "SQLConnector",
    "available_kinds",
    "build_connector",
    "build_connector_by_name",
    "load_source_config",
    "register_connector",
]

