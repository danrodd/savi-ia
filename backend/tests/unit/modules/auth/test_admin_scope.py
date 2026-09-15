"""Alcance del administrador: instalación vs. empresa (Fase 3, A3).

Antes había un solo rol: `is_admin` del ERP de la base contra la que el
usuario inició sesión. En una instalación con varias empresas, eso dejaba al
administrador del cliente A ver y editar las conexiones del cliente B, e
incluso **exportarlas con sus contraseñas**.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.infrastructure.config.settings import Settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http import admin as admin_module
from app.modules.auth.infrastructure.http.admin import (
    is_platform_admin,
    require_company_admin,
    require_platform_admin,
)
from app.shared.exceptions import ForbiddenError

BASE_DEFAULT = uuid4()
BASE_CLIENTE = uuid4()


@dataclass
class _BaseFalsa:
    id: UUID
    is_default: bool = False


class _RepositorioFalso:
    def __init__(self, bases: list[_BaseFalsa]) -> None:
        self._bases = bases

    async def list_all(self, *, include_inactive: bool = False) -> list[_BaseFalsa]:
        return self._bases

    async def get_default(self) -> _BaseFalsa | None:
        return next((b for b in self._bases if b.is_default), None)


def _usuario(*, es_admin: bool, base: UUID, login: str = "ADMIN") -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1, erp_database_id=base, login=login, full_name="X", is_admin=es_admin, is_active=True
    )


def _ajustes(admins: str = "") -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue]
        agent_db_engine="sqlite",
        erp_db_host="x",
        erp_db_user="x",
        erp_db_password="x",
        erp_db_name="x",
        savi_admin_logins=admins,
    )


@pytest.fixture
def una_sola_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        admin_module,
        "_erp_database_repository",
        lambda: _RepositorioFalso([_BaseFalsa(BASE_DEFAULT, is_default=True)]),
    )


@pytest.fixture
def varias_bases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        admin_module,
        "_erp_database_repository",
        lambda: _RepositorioFalso(
            [_BaseFalsa(BASE_DEFAULT, is_default=True), _BaseFalsa(BASE_CLIENTE)]
        ),
    )


# ── Instalación de una sola empresa: nada cambia ─────────────────────────


@pytest.mark.asyncio
async def test_single_database_admin_is_platform_admin(una_sola_base: None) -> None:
    """La app de escritorio es el despliegue actual: no se puede romper."""
    usuario = _usuario(es_admin=True, base=BASE_DEFAULT)

    assert await is_platform_admin(usuario, _ajustes()) is True


# ── Varias empresas: ahí aparece la distinción ───────────────────────────


@pytest.mark.asyncio
async def test_default_database_admin_is_platform_admin(varias_bases: None) -> None:
    usuario = _usuario(es_admin=True, base=BASE_DEFAULT)

    assert await is_platform_admin(usuario, _ajustes()) is True


@pytest.mark.asyncio
async def test_client_database_admin_is_not_platform_admin(varias_bases: None) -> None:
    """El hallazgo A3: este usuario podía exportar las credenciales de todos
    los clientes."""
    usuario = _usuario(es_admin=True, base=BASE_CLIENTE)

    assert await is_platform_admin(usuario, _ajustes()) is False


@pytest.mark.asyncio
async def test_client_database_admin_is_rejected_by_the_platform_guard(
    varias_bases: None,
) -> None:
    usuario = _usuario(es_admin=True, base=BASE_CLIENTE)

    with pytest.raises(ForbiddenError, match="instalación"):
        await require_platform_admin(usuario, _ajustes())


@pytest.mark.asyncio
async def test_listed_login_is_platform_admin_even_without_the_erp_flag(
    varias_bases: None,
) -> None:
    """El escape de `SAVI_ADMIN_LOGINS`: un agente de soporte puede no ser
    administrador en ninguna base y ser el dueño de su instalación."""
    usuario = _usuario(es_admin=False, base=BASE_CLIENTE, login="SOPORTE")

    assert await is_platform_admin(usuario, _ajustes(admins="SOPORTE")) is True


@pytest.mark.asyncio
async def test_plain_user_is_not_platform_admin(varias_bases: None) -> None:
    usuario = _usuario(es_admin=False, base=BASE_CLIENTE, login="JPEREZ")

    assert await is_platform_admin(usuario, _ajustes()) is False


# ── Administrador de empresa ─────────────────────────────────────────────


def test_client_database_admin_still_administers_its_own_company() -> None:
    """Quitarle la instalación no puede dejarlo sin administrar lo suyo."""
    usuario = _usuario(es_admin=True, base=BASE_CLIENTE)

    assert require_company_admin(usuario, _ajustes()) is usuario


def test_plain_user_is_not_company_admin() -> None:
    usuario = _usuario(es_admin=False, base=BASE_CLIENTE, login="JPEREZ")

    with pytest.raises(ForbiddenError):
        require_company_admin(usuario, _ajustes())
