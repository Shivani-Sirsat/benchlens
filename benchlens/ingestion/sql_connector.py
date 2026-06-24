"""SQL connector — reads records from an external SQL database.

Config keys:
    url:             SQLAlchemy URL of the source DB. Required.
                     May reference env vars via the standard ${VAR} syntax
                     (resolved by config_loader before reaching us).
    query:           Raw SQL SELECT (string). Mutually exclusive with `table`.
    table:           Table name; when set, generates `SELECT * FROM <table>`.
    watermark_field: Column for incremental filter — appended as
                     ``WHERE {watermark_field} > :watermark``.
    chunk_size:      If set, streams via pandas in chunks (default: read all).
    params:          Static bind parameters (dict).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

from benchlens.ingestion.base_connector import BaseConnector, ConnectorError
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


class SQLConnector(BaseConnector):
    kind = "sql"

    def _extract(self, watermark: Any) -> pd.DataFrame:
        url = self.config.get("url")
        if not url:
            raise ConnectorError(f"[{self.name}] SQL connector requires 'url'.")

        query = self.config.get("query")
        table = self.config.get("table")
        if not query and not table:
            raise ConnectorError(f"[{self.name}] SQL connector needs 'query' or 'table'.")

        sql, params = self._build_query(query, table, watermark)
        log.debug("[%s] executing SQL: %s | params=%s", self.name, sql, params)

        engine = create_engine(url, future=True)
        try:
            chunk_size = self.config.get("chunk_size")
            with engine.connect() as conn:
                if chunk_size:
                    frames = list(
                        pd.read_sql_query(text(sql), conn, params=params, chunksize=int(chunk_size))
                    )
                    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
                return pd.read_sql_query(text(sql), conn, params=params)
        finally:
            engine.dispose()

    def _build_query(
        self,
        query: str | None,
        table: str | None,
        watermark: Any,
    ) -> tuple[str, dict[str, Any]]:
        params: dict[str, Any] = dict(self.config.get("params") or {})
        if query:
            sql = query
            if watermark is not None and self.watermark_field and ":watermark" in sql:
                params["watermark"] = watermark
            return sql, params

        # table path
        sql = f"SELECT * FROM {table}"
        if watermark is not None and self.watermark_field:
            sql += f" WHERE {self.watermark_field} > :watermark"
            params["watermark"] = watermark
        if self.watermark_field:
            sql += f" ORDER BY {self.watermark_field} ASC"
        return sql, params
