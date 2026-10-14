"""Utilidades compartidas por las rutas de la consola: fábricas, cursores y lecturas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_clock
from app.modules.audit.application import AuditRecorder
from app.modules.audit.infrastructure import SqlAlchemyAuditRepository
from app.modules.clients.domain import (
    ClientNotFound,
)
from app.modules.clients.infrastructure import (
    SqlAlchemyClientRepository,
    SqlAlchemyLedgerRepository,
)
from app.modules.console.application import (
    ClientActions,
    InstanceActions,
    StaffActions,
    TokenActions,
)
from app.modules.console.presentation.schemas import (
    ClientOut,
)
from app.modules.console.queries import (
    ConsoleQueries,
    InstanceListItem,
)
from app.modules.enrollments.infrastructure import SqlAlchemyEnrollmentTokenRepository
from app.modules.instances.domain import InstanceNotFound
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.modules.staff.dependencies import build_auth_deps
from app.shared.clock import Clock
from app.shared.http_errors import ApiError

# ------------------------------------------------------------------ utilidades


def make_queries(request: Request, session: AsyncSession) -> ConsoleQueries:
    settings = request.app.state.settings
    return ConsoleQueries(session, get_clock(request), settings.latest_version)


def make_audit(request: Request, session: AsyncSession) -> AuditRecorder:
    return AuditRecorder(SqlAlchemyAuditRepository(session), get_clock(request))


def make_client_actions(request: Request, session: AsyncSession) -> ClientActions:
    clock: Clock = get_clock(request)
    return ClientActions(
        clients=SqlAlchemyClientRepository(session),
        instances=SqlAlchemyInstanceRepository(session),
        audit=make_audit(request, session),
        clock=clock,
        ledger=SqlAlchemyLedgerRepository(session),
    )


def make_instance_actions(request: Request, session: AsyncSession) -> InstanceActions:
    return InstanceActions(
        instances=SqlAlchemyInstanceRepository(session),
        audit=make_audit(request, session),
        clock=get_clock(request),
    )


def make_token_actions(request: Request, session: AsyncSession) -> TokenActions:
    return TokenActions(
        clients=SqlAlchemyClientRepository(session),
        tokens=SqlAlchemyEnrollmentTokenRepository(session),
        audit=make_audit(request, session),
        clock=get_clock(request),
        default_expires_hours=request.app.state.settings.enrollment_token_ttl_hours,
    )


def make_staff_actions(request: Request, session: AsyncSession) -> StaffActions:
    return StaffActions(build_auth_deps(request, session))


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def parse_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    """`<microsegundos desde epoch>_<uuid>`: seguro en una URL (sin `+` ni `:`)."""
    if not cursor:
        return None
    try:
        micros, _, ident = cursor.partition("_")
        return _EPOCH + timedelta(microseconds=int(micros)), UUID(ident)
    except ValueError as exc:
        raise ApiError(422, "validation_error", "El cursor no es válido.") from exc


def encode_cursor(at: datetime, ident: UUID) -> str:
    return f"{(at - _EPOCH) // timedelta(microseconds=1)}_{ident}"


async def instance_item(queries: ConsoleQueries, instance_id: UUID) -> InstanceListItem:
    item = await queries.get_instance(instance_id)
    if item is None:
        raise InstanceNotFound("No existe la instancia.")
    return item


async def client_out(request: Request, session: AsyncSession, client_id: UUID) -> ClientOut:
    summary = await make_queries(request, session).client_summary(client_id)
    if summary is None:
        raise ClientNotFound("No existe el cliente.")
    return ClientOut.of(summary)
