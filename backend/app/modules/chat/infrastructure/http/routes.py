"""Endpoint POST /chat con Server-Sent Events.

El cuerpo del stream son líneas SSE estándar:
    data: {"type": "text_delta", "text": "..."}\\n\\n

El frontend abre `fetch('/chat', { method:'POST', body:... })` y consume el
ReadableStream parseando líneas separadas por `\\n\\n`. Esto es lo mismo que
ya hace la SDK de SAVI en el frontend hermano (Vue 3).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.chat.application.requests import ChatRequest
from app.modules.chat.domain.entities import ChatEvent
from app.modules.chat.infrastructure.http.dependencies import SendMessageUseCaseDep

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
    use_case: SendMessageUseCaseDep,
) -> StreamingResponse:
    async def event_stream():
        async for event in use_case.execute(request.conversation_id, request.message):
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
