"""La consola web se sirve desde el mismo origen que el API, sin tapar al API."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from app.spa import CONSOLE_CSP
from tests.console_helpers import make_settings
from tests.fakes import FakeClock


@pytest.fixture
async def spa(tmp_path: Path, sqlite_url: str) -> AsyncGenerator[httpx.AsyncClient]:
    site = tmp_path / "console"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text("<html>consola</html>", encoding="utf-8")
    (site / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (site / "favicon.ico").write_text("ico", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no se sirve", encoding="utf-8")

    app = create_app(make_settings(sqlite_url, console_static_dir=str(site)), clock=FakeClock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
    await app.state.engine.dispose()


async def test_root_and_spa_routes_return_index_without_cache(spa: httpx.AsyncClient) -> None:
    for path in ("/", "/clientes/123", "/login"):
        res = await spa.get(path)
        assert res.status_code == 200
        assert res.text == "<html>consola</html>"
        assert res.headers["cache-control"] == "no-cache"
        assert res.headers["content-security-policy"] == CONSOLE_CSP


async def test_hashed_assets_are_cached_forever(spa: httpx.AsyncClient) -> None:
    res = await spa.get("/assets/app-abc123.js")
    assert res.status_code == 200
    assert res.text == "console.log(1)"
    assert "immutable" in res.headers["cache-control"]


async def test_api_routes_win_over_the_catch_all(spa: httpx.AsyncClient) -> None:
    health = await spa.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"} or "status" in health.json()
    # Un API inexistente responde JSON 404, nunca el HTML de la consola.
    for path in ("/api/v1/no-existe", "/console/api/no-existe", "/console/auth/no-existe"):
        res = await spa.get(path)
        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize(
    "path", ["/../secreto.txt", "/%2e%2e/secreto.txt", "/assets/../../secreto.txt"]
)
async def test_path_traversal_is_not_served(spa: httpx.AsyncClient, path: str) -> None:
    res = await spa.get(path)
    assert "no se sirve" not in res.text


async def test_security_headers_still_apply(spa: httpx.AsyncClient) -> None:
    res = await spa.get("/")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"


def test_missing_build_fails_fast(tmp_path: Path, sqlite_url: str) -> None:
    with pytest.raises(RuntimeError, match="no está compilada"):
        create_app(make_settings(sqlite_url, console_static_dir=str(tmp_path / "no-existe")))
