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
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.auth.infrastructure.http.dependencies import (
    CurrentUserDep,
    ResolveUserModulesUseCaseDep,
)
from app.modules.chat.application.requests import ChatRequest
from app.modules.chat.domain.entities import ChatEvent
from app.modules.chat.infrastructure.http.dependencies import ChatTurnUseCaseDep

router = APIRouter(prefix="/chat", tags=["chat"])


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
    modules_resolver: ResolveUserModulesUseCaseDep,
) -> StreamingResponse:
    # Validaciones de dominio ANTES de devolver StreamingResponse: si
    # algo falla, el handler global emite el 4xx limpio (dentro del
    # SSE ya no podemos cambiar el status code). Incluye chequeo de
    # ownership: si la conversación no es del usuario autenticado, 404.
    await use_case.validate(
        request.conversation_id,
        request.action,
        expected_owner_id=user.id,
    )

    # Resolución de módulos del usuario para este turno. Las tools del
    # knowledge filtran contra este set antes de devolver al LLM. Si
    # is_admin, pasamos None que significa "sin filtro" en las tools.
    resolution = await modules_resolver.execute(user.id, is_admin=user.is_admin)
    modules_filter = None if user.is_admin else frozenset(resolution.modules)

    async def event_stream():
        async for event in use_case.execute(
            request.conversation_id,
            request.action,
            request.message,
            allowed_modules=modules_filter,
        ):
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
