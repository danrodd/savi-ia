"""Cupos de turnos del chat (Fase 2 de seguridad).

Sin tope, cada turno con Claude levanta un subproceso del CLI y N usuarios
simultáneos son N procesos. Sin candado por conversación, dos pestañas dejan
ramas cruzadas. Ver `docs/seguridad/03-fase-2-resistencia.md`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.infrastructure.config import Settings
from app.modules.chat.infrastructure.http.concurrency import (
    acquire_turn_slot,
    active_turns,
    release_turn_slot,
    reset_for_tests,
)
from app.shared.exceptions import ConversationBusyError, RateLimitExceededError


def _settings(limit: int) -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue]
        agent_db_engine="sqlite",
        erp_db_host="x",
        erp_db_user="x",
        erp_db_password="x",
        erp_db_name="x",
        max_concurrent_chat_turns=limit,
    )


@pytest.fixture(autouse=True)
def _limpio() -> None:
    reset_for_tests()


@pytest.mark.asyncio
async def test_allows_up_to_the_limit() -> None:
    settings = _settings(2)

    await acquire_turn_slot(settings, uuid4())
    await acquire_turn_slot(settings, uuid4())

    assert active_turns() == 2


@pytest.mark.asyncio
async def test_rejects_over_the_limit() -> None:
    settings = _settings(1)
    await acquire_turn_slot(settings, uuid4())

    with pytest.raises(RateLimitExceededError) as error:
        await acquire_turn_slot(settings, uuid4())

    assert error.value.retry_after_seconds > 0
    assert "otras consultas" in error.value.detail


@pytest.mark.asyncio
async def test_slot_is_released() -> None:
    settings = _settings(1)
    conversation = uuid4()
    await acquire_turn_slot(settings, conversation)

    await release_turn_slot(conversation)

    assert active_turns() == 0
    await acquire_turn_slot(settings, uuid4())  # hay lugar de nuevo


@pytest.mark.asyncio
async def test_same_conversation_twice_is_busy() -> None:
    """Doble envío o dos pestañas sobre la misma conversación."""
    settings = _settings(5)
    conversation = uuid4()
    await acquire_turn_slot(settings, conversation)

    with pytest.raises(ConversationBusyError):
        await acquire_turn_slot(settings, conversation)


@pytest.mark.asyncio
async def test_busy_conversation_does_not_leak_the_global_slot() -> None:
    """El rechazo por conversación ocupada no puede consumir cupo global: si
    lo hiciera, insistir desde una pestaña agotaría el cupo de todos."""
    settings = _settings(5)
    conversation = uuid4()
    await acquire_turn_slot(settings, conversation)

    for _ in range(3):
        with pytest.raises(ConversationBusyError):
            await acquire_turn_slot(settings, conversation)

    assert active_turns() == 1


@pytest.mark.asyncio
async def test_different_conversations_run_together() -> None:
    settings = _settings(5)

    await acquire_turn_slot(settings, uuid4())
    await acquire_turn_slot(settings, uuid4())

    assert active_turns() == 2


@pytest.mark.asyncio
async def test_release_after_conversation_is_free_again() -> None:
    settings = _settings(5)
    conversation = uuid4()
    await acquire_turn_slot(settings, conversation)
    await release_turn_slot(conversation)

    await acquire_turn_slot(settings, conversation)

    assert active_turns() == 1


@pytest.mark.asyncio
async def test_release_never_goes_negative() -> None:
    """Un `finally` que corre dos veces no debe regalar cupo infinito."""
    await release_turn_slot(None)
    await release_turn_slot(None)

    assert active_turns() == 0
