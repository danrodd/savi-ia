"""`POST /chat` corta con `409` ANTES de abrir el `StreamingResponse`
cuando la base de la conversación dejó de estar disponible.

El orden importa: dentro de un SSE ya no se puede cambiar el status
code, así que la decisión tiene que tomarse antes de `return
StreamingResponse(...)`. Esta es exactamente la línea que lo hace
(`chat/infrastructure/http/routes.py`) — se llama al handler HTTP
directo, sin ASGI ni el sistema de dependencias de FastAPI (los tipos
`XDep` son solo `Annotated[X, Depends(...)]`; llamar la función a mano
los ignora), con dobles mínimos: no hace falta un `ChatTurnUseCase` real
con su runner y sus writers para probar esta única decisión, que vive
en el endpoint, no en el caso de uso.
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
from app.modules.chat.domain.interfaces import ActiveProvider, ActiveProviderResolver
from app.modules.chat.infrastructure.http.routes import chat
from app.modules.erp_databases.domain.exceptions import ErpDatabaseUnavailableError

_CONVERSATION_ID = uuid4()
_DATABASE_ID = uuid4()


class _StubChatTurnUseCase:
    """Solo `validate()`: es lo único que el endpoint llama antes del
    chequeo de disponibilidad."""

    async def validate(
        self,
        conversation_id: UUID,
        action: ChatAction,
        *,
        expected_owner: object | None = None,
    ) -> UUID:
        return _DATABASE_ID


class _StubModulesResolver:
    def __init__(self, access: DatabaseAccess) -> None:
        self._access = access

    async def execute(
        self, login: str, database_id: UUID, *, identity: object = None
    ) -> DatabaseAccess:
        return self._access


class _StubProviderResolver:
    """Siempre hay proveedor: no es lo que se está probando acá."""

    async def resolve(self) -> ActiveProvider:
        return ActiveProvider(
            kind="claude",
            chat_model="claude-sonnet-4-6",
            title_model="claude-haiku-4-5",
            credential_kind="local_session",
        )


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        login="ADMIN",
        full_name="Administrador",
        is_admin=True,
        is_active=True,
        erp_database_id=uuid4(),
    )


def _request(action: ChatAction = ChatAction.SEND) -> ChatRequest:
    return ChatRequest(
        conversation_id=_CONVERSATION_ID,
        action=action,
        message="hola" if action != ChatAction.REGENERATE else None,
    )


async def test_raises_409_before_returning_the_streaming_response() -> None:
    # `_StubChatTurnUseCase`/`_StubModulesResolver` no heredan de las
    # clases reales (no hace falta un runner ni writers para esta única
    # decisión) — el `cast` documenta que el duck-typing es deliberado.
    use_case = cast(ChatTurnUseCase, _StubChatTurnUseCase())
    resolver = cast(
        ResolveModulesForDatabaseUseCase,
        _StubModulesResolver(DatabaseAccess(has_access=False, modules=frozenset())),
    )

    provider_resolver = cast(ActiveProviderResolver, _StubProviderResolver())

    with pytest.raises(ErpDatabaseUnavailableError) as excinfo:
        await chat(_request(), use_case, _user(), resolver, provider_resolver)

    assert str(_DATABASE_ID) == excinfo.value.database_id


async def test_streams_when_the_database_is_available() -> None:
    """Contraprueba: con acceso, el endpoint sigue de largo (no levanta)."""
    use_case = cast(ChatTurnUseCase, _StubChatTurnUseCase())
    resolver = cast(
        ResolveModulesForDatabaseUseCase,
        _StubModulesResolver(
            DatabaseAccess(has_access=True, modules=frozenset(), is_admin_in_database=True)
        ),
    )

    provider_resolver = cast(ActiveProviderResolver, _StubProviderResolver())

    response = await chat(_request(), use_case, _user(), resolver, provider_resolver)

    assert response.media_type == "text/event-stream"
