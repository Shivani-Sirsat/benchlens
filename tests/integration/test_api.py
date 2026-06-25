"""Integration tests for the BenchLens REST API.

Uses fastapi.testclient.TestClient against the real Postgres warehouse, so
the suite skips automatically if Postgres is unreachable. Auth uses the
in-memory UserStore seeded by `init_auth_state` with the default demo users
(admin / viewer).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from benchlens.utils.db import ping

pytestmark = pytest.mark.skipif(
    not ping(),
    reason="local Postgres warehouse not reachable; skipping API integration tests.",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Build a TestClient once per module with fresh auth state."""
    from benchlens.api import deps
    from benchlens.api.app import create_app

    # Reset auth singletons to a known state (admin/admin, viewer/viewer).
    deps._user_store = None
    deps._jwt_config = None
    deps.init_auth_state()

    app = create_app()
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    r = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def viewer_token(client: TestClient) -> str:
    r = client.post("/auth/login", data={"username": "viewer", "password": "viewer"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def test_health_is_public(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert "version" in body


def test_root_is_public(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "BenchLens API"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_login_rejects_bad_password(client: TestClient) -> None:
    r = client.post("/auth/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_rejects_unknown_user(client: TestClient) -> None:
    r = client.post("/auth/login", data={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_login_returns_token_with_role(client: TestClient) -> None:
    r = client.post("/auth/login", data={"username": "viewer", "password": "viewer"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "viewer"
    assert body["username"] == "viewer"
    assert body["access_token"]


def test_me_requires_token(client: TestClient) -> None:
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_returns_identity(client: TestClient, admin_token: str) -> None:
    r = client.get("/auth/me", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body == {"username": "admin", "role": "admin"}


def test_invalid_token_rejected(client: TestClient) -> None:
    r = client.get("/auth/me", headers=_auth("not.a.token"))
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def test_list_kpis_requires_auth(client: TestClient) -> None:
    r = client.get("/kpis")
    assert r.status_code == 401


def test_list_kpis(client: TestClient, viewer_token: str) -> None:
    r = client.get("/kpis", headers=_auth(viewer_token))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) >= 1
    # Schema sanity.
    codes = {k["code"] for k in body}
    assert "throughput" in codes


def test_list_workloads(client: TestClient, viewer_token: str) -> None:
    r = client.get("/workloads", headers=_auth(viewer_token))
    assert r.status_code == 200
    codes = {w["code"] for w in r.json()}
    assert "llama-inference-7b" in codes


def test_list_hardware_filter(client: TestClient, viewer_token: str) -> None:
    r = client.get("/hardware?accelerator_type=GPU", headers=_auth(viewer_token))
    assert r.status_code == 200
    rows = r.json()
    assert all(h["accelerator_type"] == "GPU" for h in rows)


def test_list_stacks(client: TestClient, viewer_token: str) -> None:
    r = client.get("/stacks", headers=_auth(viewer_token))
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()}
    assert "pytorch-2.5-cuda12" in codes


def test_list_models(client: TestClient, viewer_token: str) -> None:
    r = client.get("/models", headers=_auth(viewer_token))
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def test_list_runs_requires_auth(client: TestClient) -> None:
    r = client.get("/runs")
    assert r.status_code == 401


def test_list_runs(client: TestClient, viewer_token: str) -> None:
    r = client.get("/runs?limit=5", headers=_auth(viewer_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "meta" in body
    assert body["meta"]["limit"] == 5


def test_get_run_404(client: TestClient, viewer_token: str) -> None:
    r = client.get("/runs/999999999", headers=_auth(viewer_token))
    assert r.status_code == 404


def test_get_run_returns_kpis_when_present(
    client: TestClient, viewer_token: str
) -> None:
    """If any runs exist in the warehouse, fetching one returns its KPIs."""
    listing = client.get("/runs?limit=1", headers=_auth(viewer_token)).json()
    if not listing["items"]:
        pytest.skip("No runs in warehouse to detail-test against.")
    run_id = listing["items"][0]["run_id"]
    r = client.get(f"/runs/{run_id}", headers=_auth(viewer_token))
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run_id
    assert isinstance(body["kpis"], list)


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def test_list_quality_rules(client: TestClient, viewer_token: str) -> None:
    r = client.get("/quality/rules", headers=_auth(viewer_token))
    assert r.status_code == 200
    rules = r.json()
    assert isinstance(rules, list) and len(rules) >= 1
    types = {x["type"] for x in rules}
    # config/dq_rules.yaml ships all three types.
    assert {"range", "freshness", "regression"} <= types


def test_list_quality_findings(client: TestClient, viewer_token: str) -> None:
    r = client.get("/quality/findings?limit=10", headers=_auth(viewer_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "meta" in body


# ---------------------------------------------------------------------------
# ETL audit
# ---------------------------------------------------------------------------

def test_list_etl_runs(client: TestClient, viewer_token: str) -> None:
    r = client.get("/etl/runs?limit=5", headers=_auth(viewer_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "meta" in body
