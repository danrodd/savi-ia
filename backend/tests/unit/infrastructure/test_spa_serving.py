"""Serving del frontend desde FastAPI (instalación de escritorio).

El .exe sirve API y SPA desde el mismo origen. Tres reglas que se rompen
en silencio si alguien reordena rutas o toca el fallback:

1. Las rutas de `vue-router` tienen que devolver `index.html`
   (`createWebHistory` no funciona sin ese fallback).
2. Una ruta desconocida bajo un prefijo del API tiene que ser 404 JSON,
   no HTML.
3. El path del cliente no puede escaparse del directorio del build.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.infrastructure.config import get_settings


@pytest.fixture
def spa_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "savi.db"))
    for name in ("HOST", "USER", "PASSWORD", "NAME"):
        monkeypatch.setenv(f"ERP_DB_{name}", "irrelevante-para-este-test")
    get_settings.cache_clear()

    dist = tmp_path / "frontend"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!DOCTYPE html><title>SAVI</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('savi')", encoding="utf-8")
    # Archivo fuera del build: nada servido debería poder alcanzarlo.
    (tmp_path / "secreto.txt").write_text("ANTHROPIC_API_KEY=sk-real", encoding="utf-8")

    monkeypatch.setattr(main_module, "resource_dir", lambda: tmp_path)
    # Sin context manager: no se dispara el lifespan, así que no hace
    # falta una BD real para probar el ruteo.
    client = TestClient(main_module.create_app())
    yield client
    get_settings.cache_clear()


@pytest.mark.parametrize("route", ["/", "/perfil", "/consumo", "/c/abc", "/share/xyz"])
def test_vue_router_routes_fall_back_to_index(spa_client: TestClient, route: str) -> None:
    response = spa_client.get(route)
    assert response.status_code == 200
    assert "<title>SAVI</title>" in response.text


@pytest.mark.parametrize(
    "route", ["/admin", "/admin/consumo", "/admin/conocimiento", "/admin/bases", "/admin/ia"]
)
def test_admin_screens_fall_back_to_index(spa_client: TestClient, route: str) -> None:
    """Regresión: bajo `/admin` conviven el API y las pantallas del frontend.

    El fallback comparaba solo el PRIMER segmento contra los prefijos del
    API, así que **toda** pantalla de administración devolvía un 404 JSON al
    recargarla o entrar por enlace directo en la app instalada. En desarrollo
    no se veía porque ahí la SPA la sirve Vite.
    """
    response = spa_client.get(route)

    assert response.status_code == 200
    assert "<title>SAVI</title>" in response.text


def test_real_asset_is_served(spa_client: TestClient) -> None:
    response = spa_client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.text == "console.log('savi')"


@pytest.mark.parametrize(
    "route",
    [
        "/conversations/no-existe/nada",
        "/auth/no-existe",
        "/usage/no-existe",
        "/chat/no-existe",
        # Las del API bajo /admin siguen siendo 404 JSON, no la SPA.
        "/admin/company-documents/ruta/que/no/existe",
        "/admin/erp-databases/ruta/que/no/existe",
        "/admin/llm-providers/ruta/que/no/existe",
    ],
)
def test_unknown_api_routes_stay_json_404(spa_client: TestClient, route: str) -> None:
    response = spa_client.get(route)
    assert response.status_code == 404
    assert "<!DOCTYPE html>" not in response.text


def test_traversal_cannot_escape_the_build_directory(spa_client: TestClient) -> None:
    for route in ("/../secreto.txt", "/%2e%2e/secreto.txt", "/assets/../../secreto.txt"):
        response = spa_client.get(route)
        assert "ANTHROPIC_API_KEY" not in response.text
