"""Endpoint POST /chat con Server-Sent Events.

Body discriminado por `action`:
- `send`: envío normal de un mensaje del usuario.
- `edit_last`: reemplaza el último user activo + regenera la respuesta.
- `regenerate`: regenera la última respuesta sin tocar el user.

El cuerpo del stream son líneas SSE estándar:
    data: {"type": "text_delta", "text": "..."}\\n\\n
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.infrastructure.config import get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import CurrentUserDep
from app.modules.chat.application.requests import ChatRequest
from app.modules.chat.domain.entities import ChatEvent
from app.modules.chat.infrastructure.http.dependencies import (
    ActiveProviderResolverDep,
    ChatTurnUseCaseDep,
    TurnConversationRepositoryDep,
)
from app.modules.chat.infrastructure.http.turn_registry import (
    RunningTurn,
    get_turn_registry,
)
from app.modules.company_knowledge.application.access import build_access_context
from app.modules.company_knowledge.domain.services import TurnDocumentContext
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.erp_databases.domain.exceptions import ErpDatabaseUnavailableError
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ResolveModulesForDatabaseUseCaseDep,
)
from app.shared.exceptions import NotFoundError
from app.shared.rate_limit import enforce_chat_limits

log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _require(database_id: UUID | None) -> UUID:
    """La conversación siempre tiene base (lo garantiza su creación).
    Las legadas sin base ya fallaron el chequeo de ownership arriba."""
    assert database_id is not None  # noqa: S101
    return database_id


def _require_database(user: AuthenticatedUser) -> UUID:
    """Base del ERP del usuario. Nunca es `None`: el token ya no se
    puede decodificar sin ella."""
    assert user.erp_database_id is not None  # noqa: S101
    return user.erp_database_id


def _event_to_payload(event: ChatEvent) -> dict[str, Any]:
    payload = asdict(event)
    payload["type"] = event.type.value
    return payload


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(
    request: ChatRequest,
    use_case: ChatTurnUseCaseDep,
    user: CurrentUserDep,
    modules_resolver: ResolveModulesForDatabaseUseCaseDep,
    provider_resolver: ActiveProviderResolverDep,
) -> StreamingResponse:
    # Primero el límite por usuario: cada turno cuesta dinero de verdad, así
    # que no conviene pagar ni las validaciones de un pedido que va a 429.
    enforce_chat_limits(get_settings(), user)

    # Validaciones de dominio ANTES de devolver StreamingResponse: si
    # algo falla, el handler global emite el 4xx limpio (dentro del
    # SSE ya no podemos cambiar el status code). Incluye chequeo de
    # ownership: si la conversación no es del usuario autenticado, 404.
    conversation_database_id = await use_case.validate(
        request.conversation_id,
        request.action,
        expected_owner=ConversationOwner(
            user_id=user.id,
            erp_database_id=_require_database(user),
        ),
    )

    # La base de la conversación tiene que seguir disponible: si la
    # desactivaron o eliminaron, se corta acá con un 409 limpio (dentro
    # del SSE ya no se puede cambiar el status code). El resolver, además,
    # aplica D3: los módulos se leen de ESA base, matcheando por `codigo`,
    # no se heredan de la base de identidad del usuario.
    access = await modules_resolver.execute(
        user.login, _require(conversation_database_id), identity=user
    )
    if not access.has_access:
        raise ErpDatabaseUnavailableError(
            str(conversation_database_id),
            "La base de datos de esta conversación no está disponible o ya no tenés acceso a ella.",
        )

    # Sin proveedor de IA usable, 409 `llm_provider_unavailable` acá, antes
    # del SSE. Va después de auth y ownership para no revelar el estado de
    # la configuración a quien no puede usar esta conversación.
    await provider_resolver.resolve()

    # Las tools del knowledge filtran contra este set. Un admin de la base
    # consultada pasa None = sin filtro.
    modules_filter = None if access.is_admin_in_database else frozenset(access.modules)

    # Documentos de la empresa: permisos del usuario en ESTA base. El
    # registro de citas es nuevo por turno (las referencias D1, D2… no se
    # comparten entre turnos).
    document_context = TurnDocumentContext(
        access=build_access_context(
            access,
            erp_database_id=_require(conversation_database_id),
            login=user.login,
            savi_admin_logins=get_settings().savi_admin_logins_set,
        )
    )

    settings = get_settings()

    async def producer(turno: RunningTurn) -> None:
        """Lo que corre en la TAREA del turno, ya sin conexión de por medio."""
        async for event in use_case.execute(
            request.conversation_id,
            request.action,
            request.message,
            allowed_modules=modules_filter,
            erp_database_id=conversation_database_id,
            document_context=document_context,
        ):
            turno.publish(event)

    # Arranca acá y no dentro del generador: un rechazo (429 por cupo, 409 por
    # turno en curso) tiene que salir como respuesta HTTP normal. Con el SSE
    # ya abierto no se puede cambiar el status code.
    turno = await get_turn_registry().start(settings, _require(request.conversation_id), producer)
    return _stream_response(turno)


def _stream_response(turno: RunningTurn) -> StreamingResponse:
    """SSE suscripto a un turno.

    Si el cliente se va, este generador se cancela y la tarea del turno sigue:
    esa es toda la diferencia con la versión anterior.
    """

    async def event_stream():
        async for event in turno.subscribe():
            yield _sse(_event_to_payload(event))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/activo")
async def turno_activo(
    conversation_id: UUID,
    user: CurrentUserDep,
    conversations: TurnConversationRepositoryDep,
) -> dict[str, bool]:
    """¿Hay una respuesta en curso en esta conversación?

    Lo consulta la interfaz al abrir una conversación para saber si tiene que
    reengancharse al stream en lugar de mostrar el hilo y nada más.
    """
    await _require_own_conversation(conversations, conversation_id, user)
    return {"activo": get_turn_registry().running(conversation_id)}


@router.get("/stream")
async def reenganchar(
    conversation_id: UUID,
    user: CurrentUserDep,
    conversations: TurnConversationRepositoryDep,
) -> StreamingResponse:
    """Reengancha a un turno en curso: reenvía lo emitido y sigue en vivo."""
    await _require_own_conversation(conversations, conversation_id, user)
    turno = get_turn_registry().get(conversation_id)
    if turno is None:
        raise NotFoundError("No hay una respuesta en curso en esta conversación.")
    return _stream_response(turno)


@router.post("/detener", status_code=status.HTTP_204_NO_CONTENT)
async def detener(
    conversation_id: UUID,
    user: CurrentUserDep,
    conversations: TurnConversationRepositoryDep,
) -> None:
    """Corta de verdad el turno en curso.

    Hace falta un endpoint porque la generación ya no depende de la conexión:
    abortar el fetch dejaría de detener nada y el botón "Detener" pasaría a
    mentir. Idempotente: si no había turno, igual responde 204.
    """
    await _require_own_conversation(conversations, conversation_id, user)
    get_turn_registry().cancel(conversation_id)


async def _require_own_conversation(
    conversations: ConversationRepository, conversation_id: UUID, user: AuthenticatedUser
) -> None:
    """404 si la conversación no es del usuario.

    Mismo criterio que el resto: no se distingue "no existe" de "no es tuya".

    El repositorio es el de transacción corta, no el de la sesión del request:
    `/chat/stream` devuelve un SSE que puede durar minutos y la sesión del
    request vive hasta que la respuesta termina — sería una conexión del pool
    retenida todo el reenganche, por una lectura de una fila.
    """
    conversation = await conversations.get_by_id(conversation_id)
    # Se compara contra `owner_erp_database_id` (la base con la que el dueño
    # inició sesión) y NO contra `erp_database_id` (la base que se consulta):
    # desde D10 un usuario abre conversaciones de varios clientes sin cambiar
    # de sesión, así que la segunda no identifica al dueño.
    if (
        conversation is None
        or conversation.user_id != user.id
        or conversation.owner_erp_database_id != user.erp_database_id
    ):
        raise NotFoundError("Conversación no encontrada.")
