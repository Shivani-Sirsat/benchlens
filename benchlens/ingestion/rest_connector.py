"""REST connector — pulls records from an HTTP API with pagination + auth.

Config keys:
    url:             Base endpoint URL. Required.
    method:          GET | POST (default GET).
    auth:            { type: "bearer", token_env: "VAR" } | { type: "basic", user/password_env }
    params:          Static query parameters (dict).
    headers:         Static request headers (dict).
    page_size:       Items per page (default 100).
    page_param:      Query parameter name for page number (default "page").
    size_param:      Query parameter name for page size (default "page_size").
    records_path:    Dotted path within the response JSON to the records array.
    has_more_path:   Dotted path to a boolean indicating more pages exist.
    cursor_path:     Dotted path to a cursor value used in the next request.
    cursor_param:    Query parameter to send the cursor on subsequent requests.
    timeout_seconds: Per-request timeout (default 30).
    max_pages:       Safety cap (default 1000).
    watermark_field: Field on each record for incremental loads.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd

from benchlens.ingestion.base_connector import BaseConnector, ConnectorError
from benchlens.utils.logger import get_logger

log = get_logger(__name__)


class RESTConnector(BaseConnector):
    kind = "rest"

    def _extract(self, watermark: Any) -> pd.DataFrame:
        url = self.config.get("url")
        if not url:
            raise ConnectorError(f"[{self.name}] REST connector requires 'url'.")

        method = self.config.get("method", "GET").upper()
        headers = dict(self.config.get("headers") or {})
        params = dict(self.config.get("params") or {})
        page_size = int(self.config.get("page_size", 100))
        page_param = self.config.get("page_param", "page")
        size_param = self.config.get("size_param", "page_size")
        records_path = self.config.get("records_path")
        has_more_path = self.config.get("has_more_path")
        cursor_path = self.config.get("cursor_path")
        cursor_param = self.config.get("cursor_param")
        timeout = float(self.config.get("timeout_seconds", 30))
        max_pages = int(self.config.get("max_pages", 1000))

        self._apply_auth(headers)

        if watermark is not None and self.watermark_field:
            params.setdefault("since", str(watermark))

        params.setdefault(size_param, page_size)

        all_records: list[dict] = []
        cursor: Any | None = None
        with httpx.Client(timeout=timeout) as client:
            for page in range(1, max_pages + 1):
                if cursor is not None and cursor_param:
                    params[cursor_param] = cursor
                else:
                    params[page_param] = page

                log.debug("[%s] %s %s params=%s", self.name, method, url, params)
                resp = client.request(method, url, headers=headers, params=params)
                resp.raise_for_status()
                body = resp.json()

                page_records = _dig(body, records_path) if records_path else body
                if isinstance(page_records, dict):
                    page_records = [page_records]
                if not page_records:
                    log.debug("[%s] page %d empty; stopping.", self.name, page)
                    break

                all_records.extend(page_records)
                log.debug("[%s] page %d fetched %d records (total=%d).",
                          self.name, page, len(page_records), len(all_records))

                cursor = _dig(body, cursor_path) if cursor_path else None
                has_more = bool(_dig(body, has_more_path)) if has_more_path else (
                    len(page_records) >= page_size
                )
                if cursor_path and not cursor:
                    break
                if not cursor_path and not has_more:
                    break

        return pd.json_normalize(all_records) if all_records else pd.DataFrame()

    def _apply_auth(self, headers: dict[str, str]) -> None:
        auth = self.config.get("auth") or {}
        atype = (auth.get("type") or "").lower()
        if atype == "bearer":
            token_env = auth.get("token_env")
            if not token_env:
                raise ConnectorError(f"[{self.name}] bearer auth requires 'token_env'.")
            token = os.environ.get(token_env)
            if not token:
                raise ConnectorError(
                    f"[{self.name}] env var {token_env} is empty; cannot authenticate."
                )
            headers["Authorization"] = f"Bearer {token}"
        elif atype == "basic":
            user = auth.get("user")
            pw_env = auth.get("password_env")
            pw = os.environ.get(pw_env or "", "") if pw_env else ""
            if user and pw:
                import base64
                creds = base64.b64encode(f"{user}:{pw}".encode()).decode()
                headers["Authorization"] = f"Basic {creds}"
        elif atype and atype != "none":
            log.warning("[%s] unknown auth type %r; ignoring.", self.name, atype)


def _dig(obj: Any, dotted: str | None) -> Any:
    """Navigate a dotted path in a nested dict; returns None if any part missing."""
    if not dotted:
        return obj
    cur: Any = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur
