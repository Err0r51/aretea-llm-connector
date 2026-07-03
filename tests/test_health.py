"""AC3 (code side) — ``/health`` is served UNAUTHENTICATED and reports the deploy identity.

These exercise OUR code end-to-end through a real Starlette ASGI stack — no external service is
mocked. The auth-present case constructs the **real** ``GoogleProvider`` (with placeholder config;
its token verifier makes no network call to reject a missing token) to prove the load-bearing spike:
``/health`` sits OUTSIDE the auth chain while ``/mcp`` is genuinely guarded. The live AC3 (real SHA
from a deployed container) stays a manual/integration check per repo policy.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from aretea_drive_mcp import health as health_mod
from aretea_drive_mcp.auth.provider import build_provider
from aretea_drive_mcp.health import health_payload, register_health
from cryptography.fernet import Fernet
from fastmcp import FastMCP
from pydantic import SecretStr
from starlette.testclient import TestClient

PAYLOAD_KEYS = {"status", "commit", "version", "region"}


def test_health_payload_reads_railway_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    monkeypatch.setenv("RAILWAY_REPLICA_REGION", "europe-west4-drams3a")
    payload = health_payload()
    assert payload["status"] == "ok"
    assert payload["commit"] == "abc123"
    assert payload["region"] == "europe-west4-drams3a"
    assert payload["version"] == health_mod.__version__


def test_health_payload_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    # Local/test: the Railway vars are absent → honest "unknown", never a fabricated SHA.
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_REPLICA_REGION", raising=False)
    payload = health_payload()
    assert payload["commit"] == "unknown"
    assert payload["region"] == "unknown"


def test_health_payload_treats_blank_env_as_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    # Railway can inject the var as an empty/whitespace string (e.g. a non-git-sourced deploy);
    # os.environ.get(k, default) would let that blank through as a misleading commit/region.
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "")
    monkeypatch.setenv("RAILWAY_REPLICA_REGION", "   ")
    payload = health_payload()
    assert payload["commit"] == "unknown"
    assert payload["region"] == "unknown"


def test_health_is_public_and_well_formed_on_bare_app() -> None:
    app = FastMCP(name="test")
    register_health(app)
    with TestClient(app.http_app(path="/mcp")) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert set(resp.json()) == PAYLOAD_KEYS


def _auth_app(tmp_path: Path) -> FastMCP:
    """A FastMCP wired with the REAL identity-only GoogleProvider (placeholder config)."""
    settings = SimpleNamespace(
        google_oauth_client_id="test-client",
        google_oauth_client_secret=SecretStr("test-secret"),
        public_server_url="https://example.invalid",
        jwt_signing_key=SecretStr("k" * 32),
        storage_encryption_key=SecretStr(Fernet.generate_key().decode()),
        storage_dir=str(tmp_path),
    )
    app = FastMCP(name="test", auth=build_provider(settings))
    register_health(app)
    return app


def test_health_bypasses_auth_while_mcp_is_guarded(tmp_path: Path) -> None:
    # The spike, proven: with the auth stack present, /health needs no bearer token (200) but the
    # /mcp endpoint rejects an unauthenticated call (401). So /health's openness is real and scoped.
    with TestClient(_auth_app(tmp_path).http_app(path="/mcp")) as client:
        health_resp = client.get("/health")
        mcp_resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert health_resp.status_code == 200
    assert set(health_resp.json()) == PAYLOAD_KEYS
    assert mcp_resp.status_code == 401
