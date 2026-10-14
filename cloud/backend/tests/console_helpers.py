"""Entorno de pruebas de la consola del staff (SQLite + reloj controlado)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.modules.audit.domain import RequestContext
from app.modules.staff.application import (
    AuthDeps,
    CreateStaffUseCase,
)
from app.modules.staff.domain import Role
from app.modules.staff.infrastructure import SqlAlchemySessionRepository, SqlAlchemyStaffRepository
from app.modules.staff.security import StaffSecurity, totp_code
from tests.fakes import FakeClock

CONSOLE_SECRET = "s" * 40
GOOD_PASSWORD = "una-contrasena-larga-y-rara-2026"

LOGIN = "/console/auth/login"
MFA = "/console/auth/mfa"
MFA_SETUP = "/console/auth/mfa/setup"
MFA_CONFIRM = "/console/auth/mfa/setup/confirm"
REFRESH = "/console/auth/refresh"
LOGOUT = "/console/auth/logout"
ME = "/console/api/me"


@dataclass
class Session:
    """Una sesión de consola lista para usar (access token + cookie de refresh en el cliente)."""

    email: str
    access_token: str
    totp_secret: str
    password: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@dataclass
class ConsoleEnv:
    http: httpx.AsyncClient
    app: FastAPI
    clock: FakeClock
    secrets_by_email: dict[str, str] = field(default_factory=lambda: {})

    @property
    def maker(self) -> async_sessionmaker[AsyncSession]:
        maker: async_sessionmaker[AsyncSession] = self.app.state.sessionmaker
        return maker

    def code(self, secret: str, offset: int = 0) -> str:
        return totp_code(secret, int(self.clock.now.timestamp() // 30) + offset)

    async def create_staff(self, email: str, role: Role = Role.ADMIN) -> str:
        """Crea un usuario y devuelve su contraseña temporal."""
        security: StaffSecurity = self.app.state.staff_security
        async with self.maker() as s, s.begin():
            from app.modules.audit.application import AuditRecorder
            from app.modules.audit.infrastructure import SqlAlchemyAuditRepository

            deps = AuthDeps(
                users=SqlAlchemyStaffRepository(s),
                sessions=SqlAlchemySessionRepository(s),
                audit=AuditRecorder(SqlAlchemyAuditRepository(s), self.clock),
                security=security,
                clock=self.clock,
            )
            created = await CreateStaffUseCase(deps).execute(
                email=email, full_name="Persona de Prueba", role=role, ctx=RequestContext()
            )
        return created.temporary_password

    async def onboard(
        self, email: str, role: Role = Role.ADMIN, password: str = GOOD_PASSWORD
    ) -> Session:
        """Alta + primer ingreso completo (contraseña nueva y TOTP)."""
        temporary = await self.create_staff(email, role)
        login = await self.http.post(LOGIN, json={"email": email, "password": temporary})
        assert login.status_code == 200, login.text
        assert login.json()["status"] == "mfa_setup_required"
        setup_token = login.json()["token"]
        setup = await self.http.post(MFA_SETUP, json={"setup_token": setup_token})
        assert setup.status_code == 200, setup.text
        secret = setup.json()["secret"]
        confirm = await self.http.post(
            MFA_CONFIRM,
            json={
                "setup_token": setup_token,
                "code": self.code(secret),
                "new_password": password,
            },
        )
        assert confirm.status_code == 200, confirm.text
        self.secrets_by_email[email] = secret
        return Session(email, confirm.json()["access_token"], secret, password)

    async def login(self, email: str, password: str = GOOD_PASSWORD) -> Session:
        """Ingreso normal (contraseña + TOTP). Avanza un paso del reloj para evitar reuso."""
        self.clock.advance(seconds=31)
        secret = self.secrets_by_email[email]
        step1 = await self.http.post(LOGIN, json={"email": email, "password": password})
        assert step1.status_code == 200, step1.text
        assert step1.json()["status"] == "mfa_required"
        step2 = await self.http.post(
            MFA, json={"mfa_token": step1.json()["token"], "code": self.code(secret)}
        )
        assert step2.status_code == 200, step2.text
        return Session(email, step2.json()["access_token"], secret, password)

    async def audit_actions(self) -> list[str]:
        async with self.maker() as s:
            rows = await s.execute(text("SELECT action FROM audit_log ORDER BY occurred_at, id"))
            return [r[0] for r in rows]

    async def audit_rows_text(self) -> str:
        async with self.maker() as s:
            rows = await s.execute(text("SELECT before, after, actor_email FROM audit_log"))
            return " ".join(str(tuple(r)) for r in rows)


def make_settings(sqlite_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": sqlite_url,
        "env": "test",
        "console_secret": CONSOLE_SECRET,
        "console_cookie_secure": False,
    }
    values.update(overrides)
    return Settings(**values)
