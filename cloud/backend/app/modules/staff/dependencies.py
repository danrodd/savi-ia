"""Dependencias HTTP de la consola: servicio de seguridad, contexto y permisos."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_clock, transaction
from app.modules.audit.application import AuditRecorder
from app.modules.audit.domain import RequestContext
from app.modules.audit.infrastructure import SqlAlchemyAuditRepository
from app.modules.staff.application import AuthDeps, AuthenticateStaffUseCase, Principal
from app.modules.staff.domain import InvalidSessionToken, Permission, has_permission
from app.modules.staff.infrastructure import SqlAlchemySessionRepository, SqlAlchemyStaffRepository
from app.modules.staff.security import StaffSecurity
from app.shared.http_errors import ApiError

BEARER_SCHEME = "bearer"


def staff_security(request: Request) -> StaffSecurity:
    security: StaffSecurity | None = request.app.state.staff_security
    if security is None:
        raise ApiError(
            503, "console_disabled", "La consola no está configurada (falta CLOUD_CONSOLE_SECRET)."
        )
    return security


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def request_context(request: Request, principal: Principal | None = None) -> RequestContext:
    return RequestContext(
        actor_staff_id=principal.user.id if principal else None,
        actor_email=principal.user.email if principal else None,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def build_auth_deps(request: Request, session: AsyncSession) -> AuthDeps:
    clock = get_clock(request)
    return AuthDeps(
        users=SqlAlchemyStaffRepository(session),
        sessions=SqlAlchemySessionRepository(session),
        audit=AuditRecorder(SqlAlchemyAuditRepository(session), clock),
        security=staff_security(request),
        clock=clock,
    )


async def authenticate(request: Request) -> Principal:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != BEARER_SCHEME or not token.strip():
        raise ApiError(401, "unauthorized", "Iniciá sesión para continuar.")
    async with transaction(request) as session:
        try:
            return await AuthenticateStaffUseCase(build_auth_deps(request, session)).execute(
                token.strip()
            )
        except InvalidSessionToken as exc:
            raise ApiError(401, "unauthorized", "Iniciá sesión para continuar.") from exc


class RequirePermission:
    """Dependencia de ruta: exige sesión válida y un permiso de la matriz.

    Toda ruta de `/console/api` debe declararla; un test recorre el router y falla si falta.
    """

    def __init__(self, permission: Permission) -> None:
        self.permission = permission

    async def __call__(self, request: Request) -> Principal:
        principal = await authenticate(request)
        if not has_permission(principal.user.role, self.permission):
            raise ApiError(403, "forbidden", "No tenés permiso para esta acción.")
        return principal
