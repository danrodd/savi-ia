"""La documentación interactiva del API no se publica en producción.

`/docs`, `/redoc` y `/openapi.json` listan cada ruta y cada esquema a quien
llegue al servidor. SAVI publicado en internet (o en una red de empresa) no
tiene por qué regalar ese mapa.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.infrastructure.config import get_settings
from app.infrastructure.config.settings import Settings

_DOCS_ROUTES = ("/docs", "/redoc", "/openapi.json")


def _client(app_env: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    settings = Settings(  # pyright: ignore[reportCallIssue]
        erp_db_host="x",
        erp_db_user="x",
        erp_db_password="x",
        erp_db_name="x",
        # Fuera de desarrollo se exige Postgres. No se conecta: el lifespan no corre.
        agent_db_engine="postgresql",
        agent_db_host="localhost",
        agent_db_user="savi",
        agent_db_password="x",
        agent_db_name="savi",
        app_env=app_env,  # pyright: ignore[reportArgumentType]
        jwt_secret="un-secreto-generado-de-verdad",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    # Sin el build del frontend: lo que se prueba es el API, no la SPA.
    monkeypatch.setattr(main_module, "resource_dir", lambda: tmp_path)
    return TestClient(main_module.create_app())


@pytest.mark.parametrize("route", _DOCS_ROUTES)
def test_docs_are_hidden_in_production(
    route: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client("production", monkeypatch, tmp_path)

    assert client.get(route).status_code == 404


@pytest.mark.parametrize("route", _DOCS_ROUTES)
def test_docs_are_available_in_development(
    route: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client("development", monkeypatch, tmp_path)

    assert client.get(route).status_code == 200


def test_health_still_responds_in_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client("production", monkeypatch, tmp_path)

    assert client.get("/health").status_code == 200
    get_settings.cache_clear()
