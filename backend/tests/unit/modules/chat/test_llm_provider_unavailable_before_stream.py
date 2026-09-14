"""`POST /chat` corta con 409 `llm_provider_unavailable` ANTES de abrir el
`StreamingResponse` cuando no hay proveedor de IA usable.

Mismo patrón que `test_database_unavailable_before_stream.py`: se llama
al handler HTTP directo, con dobles mínimos, porque la decisión vive en
el endpoint y no en el caso de uso.
"""
from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from app.modules.auth.application.use_cases.resolve_modules_for_database import (
    DatabaseAccess,
    ResolveModulesForDatabaseUseCase,
)
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.chat.application.requests import ChatAction, ChatRequest
from app.modules.chat.application.use_cases import ChatTurnUseCase
from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.chat.domain.interfaces import ActiveProvider, ActiveProviderResolver
from app.modules.chat.infrastructure.http.routes import chat

_CONVERSATION_ID = uuid4()
_DATABASE_ID = uuid4()


class _StubChatTurnUseCase:
    async def validate(
        self,
        conversation_id: UUID,
        action: ChatAction,
        *,
        expected_owner: object | None = None,
    ) -> UUID:
        return _DATABASE_ID


class _AvailableModulesResolver:
    async def execute(self, login: str, database_id: UUID) -> DatabaseAccess:
        return DatabaseAccess(has_access=True, modules=frozenset(), is_admin_in_database=True)


class _UnavailableProviderResolver:
    async def resolve(self) -> ActiveProvider:
        raise LlmProviderUnavailableError("No hay un proveedor de IA activo.")


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        login="ADMIN",
        full_name="Administrador",
        is_admin=True,
        is_active=True,
        erp_database_id=uuid4(),
    )


def _request() -> ChatRequest:
    return ChatRequest(conversation_id=_CONVERSATION_ID, action=ChatAction.SEND, message="hola")


async def test_raises_409_before_returning_the_streaming_response() -> None:
    use_case = cast(ChatTurnUseCase, _StubChatTurnUseCase())
    modules_resolver = cast(ResolveModulesForDatabaseUseCase, _AvailableModulesResolver())
    provider_resolver = cast(ActiveProviderResolver, _UnavailableProviderResolver())

    with pytest.raises(LlmProviderUnavailableError):
        await chat(_request(), use_case, _user(), modules_resolver, provider_resolver)
