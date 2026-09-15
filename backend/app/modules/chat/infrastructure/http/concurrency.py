"""Cupos de turnos del chat: cuántos a la vez y uno por conversación.

Dos candados distintos, por motivos distintos:

- **Cupo global**: un turno con Claude levanta un subproceso del CLI con su
  contexto. Sin tope, N usuarios simultáneos son N procesos y la máquina se
  queda sin memoria antes de que termine ninguno. Se rechaza rápido con 429 en
  lugar de encolar: un chat que tarda tres minutos en arrancar es peor que un
  "probá de nuevo".
- **Candado por conversación**: sin esto, dos pestañas o un doble envío corren
  `send`/`edit_last`/`regenerate` a la vez sobre la misma conversación y dejan
  ramas cruzadas (dos mensajes de usuario activos, supersedes pisados).

Un contador explícito y no `asyncio.Semaphore`: lo que hace falta es
**rechazar** al instante cuando no hay lugar, y un semáforo solo sabe esperar.
Preguntarle si tiene cupo obliga a mirarle atributos privados.

Ambos viven en el proceso, como el resto del estado de SAVI. Cuando llegue el
modo servidor multiproceso, el candado por conversación pasa a la BD
(`SELECT … FOR UPDATE` sobre la fila) sin tocar a los llamadores.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.infrastructure.config import Settings
from app.shared.exceptions import ConversationBusyError, RateLimitExceededError

_BUSY_RETRY_AFTER_S = 5

_active_turns = 0
_busy_conversations: set[UUID] = set()
_guard = asyncio.Lock()


async def acquire_turn_slot(settings: Settings, conversation_id: UUID | None) -> None:
    """Toma cupo global y candado de la conversación, o rechaza en el acto.

    Dos funciones sueltas y no un `async with`: el cupo se toma en el handler
    (para que un rechazo salga como 429 HTTP normal) y se suelta dentro del
    generador del SSE, que son dos ámbitos distintos. Con un context manager
    había que abrirlo y cerrarlo a mano igual, y eso se lee peor."""
    global _active_turns
    limit = max(1, settings.max_concurrent_chat_turns)

    async with _guard:
        if _active_turns >= limit:
            raise RateLimitExceededError(
                retry_after_seconds=_BUSY_RETRY_AFTER_S,
                detail="SAVI está atendiendo otras consultas. Probá en unos segundos.",
            )
        if conversation_id is not None and conversation_id in _busy_conversations:
            raise ConversationBusyError(str(conversation_id))
        _active_turns += 1
        if conversation_id is not None:
            _busy_conversations.add(conversation_id)


async def release_turn_slot(conversation_id: UUID | None) -> None:
    """Se llama SIEMPRE desde un `finally`: sin eso, cortar el stream filtra
    el cupo y a los pocos cortes nadie puede chatear."""
    global _active_turns
    async with _guard:
        _active_turns = max(0, _active_turns - 1)
        if conversation_id is not None:
            _busy_conversations.discard(conversation_id)


def active_turns() -> int:
    """Para diagnóstico y tests."""
    return _active_turns


def reset_for_tests() -> None:
    global _active_turns
    _active_turns = 0
    _busy_conversations.clear()
