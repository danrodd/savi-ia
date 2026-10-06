"""Fase 0 de seguridad: `/health` barato y secreto de firma obligatorio.

- `/health` es público y no tiene límite de pedidos. Si toca la base, una
  ráfaga sin credenciales degrada toda la app (medido: 200 pedidos
  concurrentes llevaban la mediana a ~1 s).
- El `JWT_SECRET` de fábrica firma tokens válidos, `is_admin` incluido, para
  cualquiera que lo conozca.

Ver `docs/seguridad/01-fase-0-cierre-urgente.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main_module
from app.infrastructure.config import get_settings
from app.infrastructure.config.settings import INSECURE_JWT_SECRET, Settings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "savi.db"))
    for name in ("HOST", "USER", "PASSWORD", "NAME"):
        monkeypatch.setenv(f"ERP_DB_{name}", "irrelevante-para-este-test")
    get_settings.cache_clear()
    # Sin context manager: no se dispara el lifespan y no hace falta BD real.
    # Justamente por eso `/health` tiene que responder sin tocarla.
    yield TestClient(main_module.create_app())
    get_settings.cache_clear()


def test_health_responds_without_database(client: TestClient) -> None:
    """Sin engine inicializado: si `/health` consultara la BD, fallaría."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_db_requires_admin(client: TestClient) -> None:
    """El chequeo caro queda detrás de autenticación."""
    assert client.get("/health/db").status_code == 401


def _settings(**overrides: str) -> Settings:
    """Ajustes válidos para el entorno pedido.

    Fuera de `development` se exige Postgres (SQLite no soporta varios
    usuarios), así que estos casos traen una configuración de Postgres
    completa: lo que se prueba acá es el secreto, no el motor.
    """
    base: dict[str, str] = {
        "erp_db_host": "x",
        "erp_db_user": "x",
        "erp_db_password": "x",
        "erp_db_name": "x",
    }
    if overrides.get("app_env", "development") == "development":
        base["agent_db_engine"] = "sqlite"
    else:
        base |= {
            "agent_db_engine": "postgresql",
            "agent_db_host": "localhost",
            "agent_db_user": "savi",
            "agent_db_password": "x",
            "agent_db_name": "savi",
        }
    return Settings(**{**base, **overrides})  # pyright: ignore[reportArgumentType]


def test_default_jwt_secret_rejected_outside_development() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _settings(app_env="production", jwt_secret=INSECURE_JWT_SECRET)


def test_default_jwt_secret_rejected_in_staging() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _settings(app_env="staging", jwt_secret=INSECURE_JWT_SECRET)


def test_default_jwt_secret_allowed_in_development() -> None:
    """`uv run dev` tiene que seguir arrancando sin configurar nada."""
    settings = _settings(app_env="development", jwt_secret=INSECURE_JWT_SECRET)

    assert settings.uses_insecure_jwt_secret is True


def test_real_secret_accepted_in_production() -> None:
    settings = _settings(app_env="production", jwt_secret="un-secreto-generado-de-verdad")

    assert settings.uses_insecure_jwt_secret is False


def _sqlite_production() -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue]
        erp_db_host="x",
        erp_db_user="x",
        erp_db_password="x",
        erp_db_name="x",
        agent_db_engine="sqlite",
        app_env="production",
        jwt_secret="un-secreto-generado-de-verdad",
    )


def test_sqlite_rejected_in_production_server() -> None:
    with pytest.raises(ValidationError, match="no soporta varios usuarios"):
        _sqlite_production()


def test_sqlite_allowed_in_desktop_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    """El instalador escribe `APP_ENV=production` con SQLite por defecto: el
    `.exe` tiene que arrancar igual."""
    monkeypatch.setattr("sys.frozen", True, raising=False)

    settings = _sqlite_production()

    assert settings.agent_db_engine == "sqlite"
