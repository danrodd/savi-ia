"""Turnos fallidos para el administrador de la empresa.

Mismo guard que el resto de `/admin`: administrador de la empresa, acotado a la
base con la que inició sesión. Sirve para mandarle a soporte el código de un
turno que falló sin tener que buscar el log en el equipo del cliente.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.infrastructure.database.session import AgentSessionDep
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_company_admin
from app.modules.conversations.application.use_cases.list_failed_turns import (
    FAILED_TURNS_LIMIT_MAX,
    ListFailedTurnsUseCase,
)
from app.modules.conversations.infrastructure.persistence.repositories.sqlalchemy_failed_turn_reader import (  # noqa: E501
    SqlAlchemyFailedTurnReader,
)

router = APIRouter(prefix="/admin/failed-turns", tags=["conversations-admin"])

CompanyAdminDep = Annotated[AuthenticatedUser, Depends(require_company_admin)]


class FailedTurnResponse(BaseModel):
    message_id: UUID
    conversation_id: UUID
    conversation_title: str | None
    user_id: int | None
    created_at: datetime
    error_code: str | None
    error_message: str | None
    support_code: str | None
    provider: str | None
    model: str | None
    erp_queries: int


def get_list_failed_turns_use_case(session: AgentSessionDep) -> ListFailedTurnsUseCase:
    return ListFailedTurnsUseCase(SqlAlchemyFailedTurnReader(session))


ListFailedTurnsDep = Annotated[ListFailedTurnsUseCase, Depends(get_list_failed_turns_use_case)]


@router.get("", response_model=list[FailedTurnResponse])
async def list_failed_turns(
    user: CompanyAdminDep,
    use_case: ListFailedTurnsDep,
    limit: Annotated[int, Query(ge=1, le=FAILED_TURNS_LIMIT_MAX)] = 50,
) -> list[FailedTurnResponse]:
    assert user.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    turns = await use_case.execute(user.erp_database_id, limit)
    return [FailedTurnResponse(**turn.__dict__) for turn in turns]
