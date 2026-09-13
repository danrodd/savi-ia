"""Tests del gate de administración de SAVI (D9).

Lo que se protege: el escape `SAVI_ADMIN_LOGINS` habilita SOLO la sección
de administración, y su alcance es exactamente ese — no toca módulos del
ERP ni acceso a datos.
"""
from __future__ import annotations

from uuid import uuid4

from app.infrastructure.config.settings import Settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import is_savi_admin


def _user(*, login: str, is_admin: bool) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        erp_database_id=uuid4(),
        login=login,
        full_name="Test",
        is_admin=is_admin,
        is_active=True,
    )


def _settings(admin_logins: str = "") -> Settings:
    return Settings(  # type: ignore[call-arg]
        agent_db_engine="sqlite",
        savi_admin_logins=admin_logins,
        erp_credentials_key="sIYQBhcJUxE6vsRRrJvVKa3CtoUj_o8SPDBSAcHDCyM=",
    )


def test_erp_admin_is_savi_admin() -> None:
    assert is_savi_admin(_user(login="X", is_admin=True), _settings()) is True


def test_non_admin_without_escape_is_not_savi_admin() -> None:
    assert is_savi_admin(_user(login="JPEREZ", is_admin=False), _settings()) is False


def test_escape_list_grants_admin_to_a_non_erp_admin() -> None:
    """El caso que motiva el escape: dueño de su instalación, sin flag de
    admin en el ERP."""
    settings = _settings("SOPORTE,JPEREZ")
    assert is_savi_admin(_user(login="JPEREZ", is_admin=False), settings) is True


def test_escape_list_is_case_insensitive() -> None:
    settings = _settings("jperez")
    assert is_savi_admin(_user(login="JPEREZ", is_admin=False), settings) is True


def test_user_not_in_escape_list_stays_out() -> None:
    settings = _settings("SOPORTE")
    assert is_savi_admin(_user(login="OTRO", is_admin=False), settings) is False
