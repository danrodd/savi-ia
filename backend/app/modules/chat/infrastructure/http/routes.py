"""Endpoint POST /chat con Server-Sent Events.

Body discriminado por `action`:
- `send`: envío normal de un mensaje del usuario.
- `edit_last`: reemplaza el último user activo + regenera la respuesta.
- `regenerate`: regenera la última respuesta sin tocar el user.

El cuerpo del stream son líneas SSE estándar:
    data: {"type": "text_delta", "text": "..."}\\n\\n
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.infrastructure.config import get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import CurrentUserDep
from app.modules.chat.application.requests import ChatRequest
from app.modules.chat.domain.entities import ChatEvent
from app.modules.chat.infrastructure.http.concurrency import (
    acquire_turn_slot,
    release_turn_slot,
)
from app.modules.chat.infrastructure.http.dependencies import (
    ActiveProviderResolverDep,
    ChatTurnUseCaseDep,
)
from app.modules.company_knowledge.application.access import build_access_context
from app.modules.company_knowledge.domain.services import TurnDocumentContext
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.erp_databases.domain.exceptions import ErpDatabaseUnavailableError
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ResolveModulesForDatabaseUseCaseDep,
)
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
    access = await modules_resolver.execute(user.login, _require(conversation_database_id))
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
    # El cupo se toma ACÁ y no dentro del generador: si no hay lugar, el 429
    # tiene que salir como respuesta HTTP normal. Una vez abierto el SSE ya no
    # se puede cambiar el status code.
    await acquire_turn_slot(settings, request.conversation_id)

    async def event_stream():
        try:
            async with asyncio.timeout(settings.chat_turn_timeout_seconds):
                async for event in use_case.execute(
                    request.conversation_id,
                    request.action,
                    request.message,
                    allowed_modules=modules_filter,
                    erp_database_id=conversation_database_id,
                    document_context=document_context,
                ):
                    yield _sse(_event_to_payload(event))
        except TimeoutError:
            # `max_agent_turns` acota las rondas de herramienta, no el tiempo.
            # Sin este reloj, un turno podía quedarse colgado reteniendo el
            # subproceso del CLI y la conexión. Lo ya generado se persiste por
            # el mismo camino que la cancelación del cliente.
            log.warning("chat_turn_timeout conversation_id=%s", request.conversation_id)
            yield _sse(
                {
                    "type": "error",
                    "message": (
                        "La consulta tardó demasiado y se detuvo. "
                        "Probá con una pregunta más acotada."
                    ),
                }
            )
            yield _sse({"type": "done"})
        finally:
            await release_turn_slot(request.conversation_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
