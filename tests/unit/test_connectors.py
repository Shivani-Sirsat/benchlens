"""Unit tests for ingestion connectors.

These tests are hermetic — they only touch the local filesystem and an
in-memory mock HTTP transport. No external network or DB is required.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import httpx
import pandas as pd
import pytest

from benchlens.ingestion import (
    BaseConnector,
    ConnectorError,
    CSVConnector,
    JSONConnector,
    RESTConnector,
    SQLConnector,
    available_kinds,
    build_connector,
)
from benchlens.ingestion.base_connector import STATE_DIR

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def csv_dir(tmp_path: Path) -> Path:
    target = tmp_path / "csv"
    target.mkdir()
    shutil.copy(FIXTURES / "sample_results.csv", target / "sample_results.csv")
    return target


@pytest.fixture
def json_file(tmp_path: Path) -> Path:
    target = tmp_path / "results.json"
    shutil.copy(FIXTURES / "sample_results.json", target)
    return target


@pytest.fixture
def jsonl_file(tmp_path: Path) -> Path:
    records = json.loads((FIXTURES / "sample_results.json").read_text())["records"]
    target = tmp_path / "results.jsonl"
    with target.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return target


@pytest.fixture(autouse=True)
def _isolate_watermarks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Redirect watermark storage into the test's tmp dir."""
    new_dir = tmp_path / "state"
    monkeypatch.setattr("benchlens.ingestion.base_connector.STATE_DIR", new_dir)
    yield


# ---------------------------------------------------------------------------
# CSVConnector
# ---------------------------------------------------------------------------


def test_csv_connector_extracts_all_rows(csv_dir: Path) -> None:
    conn = CSVConnector("sample_csv", {"path": str(csv_dir)})
    result = conn.run()
    assert result.rows == 10
    assert "workload_code" in result.records.columns
    assert "_source_file" in result.records.columns


def test_csv_connector_watermark_filters_rows(csv_dir: Path) -> None:
    conn = CSVConnector(
        "sample_csv",
        {"path": str(csv_dir), "watermark_field": "started_at"},
    )
    # First pass: ingest everything.
    result1 = conn.run()
    assert result1.rows == 10
    assert result1.new_watermark is not None

    # Persist that watermark, then re-run: should return 0 new rows.
    conn.commit_watermark(result1.new_watermark)
    result2 = conn.run()
    assert result2.rows == 0


def test_csv_connector_missing_path_raises(tmp_path: Path) -> None:
    conn = CSVConnector("bad", {"path": str(tmp_path / "does_not_exist")})
    with pytest.raises(ConnectorError):
        conn.run()


def test_csv_connector_disabled_returns_empty(csv_dir: Path) -> None:
    conn = CSVConnector("sample_csv", {"path": str(csv_dir), "enabled": False})
    result = conn.run()
    assert result.rows == 0


# ---------------------------------------------------------------------------
# JSONConnector
# ---------------------------------------------------------------------------


def test_json_connector_reads_records_path(json_file: Path) -> None:
    conn = JSONConnector(
        "sample_json",
        {"path": str(json_file), "format": "json", "records_path": "records"},
    )
    result = conn.run()
    assert result.rows == 5
    assert "run_id" in result.records.columns
    # Nested keys flatten with json_normalize.
    assert "kpis.throughput" in result.records.columns


def test_json_connector_reads_jsonl(jsonl_file: Path) -> None:
    conn = JSONConnector(
        "sample_jsonl",
        {"path": str(jsonl_file), "format": "jsonl"},
    )
    result = conn.run()
    assert result.rows == 5
    assert "kpis.gpu_util_pct" in result.records.columns


# ---------------------------------------------------------------------------
# RESTConnector
# ---------------------------------------------------------------------------


def _make_mock_transport(pages: list[dict]) -> httpx.MockTransport:
    """Return a transport that serves the given JSON pages in order."""
    counter = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = counter["i"]
        counter["i"] += 1
        if idx >= len(pages):
            return httpx.Response(200, json={"items": [], "has_more": False})
        return httpx.Response(200, json=pages[idx])

    return httpx.MockTransport(handler)


def test_rest_connector_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        {"items": [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}], "has_more": True},
        {"items": [{"id": 3, "v": "c"}], "has_more": False},
    ]
    transport = _make_mock_transport(pages)

    real_client = httpx.Client

    def patched_client(*args, **kwargs):  # noqa: ANN001
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("benchlens.ingestion.rest_connector.httpx.Client", patched_client)

    conn = RESTConnector(
        "mock_api",
        {
            "url": "https://example.test/runs",
            "records_path": "items",
            "has_more_path": "has_more",
            "page_size": 2,
        },
    )
    result = conn.run()
    assert result.rows == 3
    assert list(result.records["id"]) == [1, 2, 3]


def test_rest_connector_requires_url() -> None:
    with pytest.raises(ConnectorError):
        RESTConnector("bad", {}).run()


# ---------------------------------------------------------------------------
# SQLConnector
# ---------------------------------------------------------------------------


def test_sql_connector_reads_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "src.db"
    url = f"sqlite:///{db.as_posix()}"

    # Seed an external SQLite DB.
    from sqlalchemy import create_engine, text

    eng = create_engine(url, future=True)
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE runs (id INTEGER PRIMARY KEY, name TEXT, ts TEXT)"
        )
        conn.exec_driver_sql(
            "INSERT INTO runs (name, ts) VALUES "
            "('a','2025-01-01'), ('b','2025-01-02'), ('c','2025-01-03')"
        )
    eng.dispose()

    conn = SQLConnector(
        "ext_db",
        {"url": url, "table": "runs", "watermark_field": "ts"},
    )
    result = conn.run()
    assert result.rows == 3
    assert result.new_watermark == "2025-01-03"


def test_sql_connector_requires_query_or_table() -> None:
    with pytest.raises(ConnectorError):
        SQLConnector("bad", {"url": "sqlite:///:memory:"}).run()


# ---------------------------------------------------------------------------
# Factory + base behaviour
# ---------------------------------------------------------------------------


def test_factory_dispatch(csv_dir: Path) -> None:
    conn = build_connector("sample_csv", {"connector": "csv", "path": str(csv_dir)})
    assert isinstance(conn, CSVConnector)
    assert "csv" in available_kinds() and "json" in available_kinds()


def test_factory_unknown_kind_raises() -> None:
    with pytest.raises(ConnectorError):
        build_connector("x", {"connector": "ftp"})


def test_factory_missing_kind_raises() -> None:
    with pytest.raises(ConnectorError):
        build_connector("x", {})


class _AlwaysFailConnector(BaseConnector):
    kind = "alwaysfail"

    def _extract(self, watermark):  # noqa: ANN001
        raise ConnectionError("boom")


def test_base_connector_retries_then_reraises() -> None:
    conn = _AlwaysFailConnector("flaky", {"retry_max_attempts": 2, "retry_backoff_seconds": 0})
    with pytest.raises((ConnectorError, ConnectionError)):
        conn.run()
