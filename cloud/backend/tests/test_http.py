from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.config import Settings
from app.main import create_app


def _client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
    )


async def test_health_does_not_touch_database() -> None:
    # Puerto 1: si /health tocara la BD, fallaría.
    settings = Settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none", env="test")
    async with _client(settings) as http:
        res = await http.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_ready_ok_with_database(sqlite_url: str) -> None:
    async with _client(Settings(database_url=sqlite_url, env="test")) as http:
        res = await http.get("/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


async def test_ready_503_without_database() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none", env="test")
    async with _client(settings) as http:
        res = await http.get("/ready")
    assert res.status_code == 503
    assert res.json() == {"status": "unavailable"}


async def test_security_headers_and_request_id(sqlite_url: str) -> None:
    async with _client(Settings(database_url=sqlite_url, env="test")) as http:
        res = await http.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["cache-control"] == "no-store"
    assert len(res.headers["x-request-id"]) == 32


async def test_cors_is_closed_by_default(sqlite_url: str) -> None:
    async with _client(Settings(database_url=sqlite_url, env="test")) as http:
        res = await http.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in res.headers


async def test_cors_allows_only_configured_origins(sqlite_url: str) -> None:
    settings = Settings(
        database_url=sqlite_url, env="test", cors_origins=["https://consola.example"]
    )
    async with _client(settings) as http:
        ok = await http.get("/health", headers={"Origin": "https://consola.example"})
        bad = await http.get("/health", headers={"Origin": "https://evil.example"})
    assert ok.headers["access-control-allow-origin"] == "https://consola.example"
    assert "access-control-allow-origin" not in bad.headers


async def test_docs_disabled_outside_development(sqlite_url: str) -> None:
    async with _client(Settings(database_url=sqlite_url, env="production")) as http:
        assert (await http.get("/docs")).status_code == 404
        assert (await http.get("/openapi.json")).status_code == 404


async def test_access_log_has_no_query_or_secrets(
    sqlite_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(database_url=sqlite_url, env="test", log_level="INFO")
    async with _client(settings) as http:
        # El cliente httpx de la prueba registra la URL completa: no es log de la app.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        await http.get(
            "/health?token=svk_enr_SECRET", headers={"Authorization": "Bearer svk_ins_SECRET"}
        )
    logging.getLogger().handlers[0].flush()
    out = capsys.readouterr().out
    assert "SECRET" not in out
    record = json.loads(next(line for line in out.splitlines() if '"request"' in line))
    assert record["path"] == "/health"
    assert record["status"] == 200
