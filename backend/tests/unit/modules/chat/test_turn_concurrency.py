"""Registro de turnos: cupos, candado por conversación y vida propia.

Dos cosas se cruzan acá. Los cupos vienen de la Fase 2 de seguridad
(`docs/seguridad/03-fase-2-resistencia.md`): sin tope, cada turno levanta un
subproceso del CLI y N usuarios simultáneos son N procesos; sin candado por
conversación, dos pestañas dejan ramas cruzadas.

Lo nuevo es que el turno ya no es el stream sino una tarea
(`docs/chat-turnos-en-segundo-plano.md`), así que el cupo se suelta cuando
termina la TAREA y no cuando se corta la conexión.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.infrastructure.config import Settings
from app.modules.chat.domain.entities import ChatEvent, TextDeltaEvent
from app.modules.chat.infrastructure.http.turn_registry import RunningTurn, TurnRegistry
from app.shared.exceptions import ConversationBusyError, RateLimitExceededError


def _settings(limit: int, timeout: float = 30.0) -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue]
        agent_db_engine="sqlite",
        erp_db_host="x",
        erp_db_user="x",
        erp_db_password="x",
        erp_db_name="x",
        max_concurrent_chat_turns=limit,
        chat_turn_timeout_seconds=timeout,
    )


def _delta(text: str) -> ChatEvent:
    return TextDeltaEvent(text=text)


async def _nunca_termina(turno: RunningTurn) -> None:
    await asyncio.Event().wait()


def _productor_controlado(arranco: asyncio.Event, seguir: asyncio.Event):
    async def producer(turno: RunningTurn) -> None:
        turno.publish(_delta("hola"))
        arranco.set()
        await seguir.wait()
        turno.publish(_delta(" mundo"))

    return producer


@pytest.fixture
def registro() -> TurnRegistry:
    return TurnRegistry()


@pytest.mark.asyncio
async def test_allows_up_to_the_limit(registro: TurnRegistry) -> None:
    settings = _settings(2)

    await registro.start(settings, uuid4(), _nunca_termina)
    await registro.start(settings, uuid4(), _nunca_termina)

    assert registro.active_count() == 2
    registro.reset_for_tests()


@pytest.mark.asyncio
async def test_rejects_over_the_limit(registro: TurnRegistry) -> None:
    settings = _settings(1)
    await registro.start(settings, uuid4(), _nunca_termina)

    with pytest.raises(RateLimitExceededError) as error:
        await registro.start(settings, uuid4(), _nunca_termina)

    assert error.value.retry_after_seconds > 0
    assert "otras consultas" in error.value.detail
    registro.reset_for_tests()


@pytest.mark.asyncio
async def test_same_conversation_twice_is_busy(registro: TurnRegistry) -> None:
    """Doble envío o dos pestañas sobre la misma conversación."""
    settings = _settings(5)
    conversation = uuid4()
    await registro.start(settings, conversation, _nunca_termina)

    with pytest.raises(ConversationBusyError):
        await registro.start(settings, conversation, _nunca_termina)

    registro.reset_for_tests()


@pytest.mark.asyncio
async def test_busy_conversation_does_not_leak_the_global_slot(
    registro: TurnRegistry,
) -> None:
    """El rechazo por conversación ocupada no puede consumir cupo global: si
    lo hiciera, insistir desde una pestaña agotaría el cupo de todos."""
    settings = _settings(5)
    conversation = uuid4()
    await registro.start(settings, conversation, _nunca_termina)

    for _ in range(3):
        with pytest.raises(ConversationBusyError):
            await registro.start(settings, conversation, _nunca_termina)

    assert registro.active_count() == 1
    registro.reset_for_tests()


@pytest.mark.asyncio
async def test_slot_is_released_when_the_task_ends(registro: TurnRegistry) -> None:
    """El cupo se suelta al terminar la tarea, no al cerrar la conexión."""
    settings = _settings(1)

    async def corto(turno: RunningTurn) -> None:
        turno.publish(_delta("listo"))

    turno = await registro.start(settings, uuid4(), corto)
    assert turno.task is not None
    await turno.task

    assert registro.active_count() == 0
    await registro.start(settings, uuid4(), _nunca_termina)  # hay lugar de nuevo
    registro.reset_for_tests()


@pytest.mark.asyncio
async def test_the_turn_survives_the_subscriber(registro: TurnRegistry) -> None:
    """El corazón del cambio: cortar el stream NO detiene la generación."""
    settings = _settings(1)
    arranco, seguir = asyncio.Event(), asyncio.Event()
    conversation = uuid4()
    turno = await registro.start(
        settings, conversation, _productor_controlado(arranco, seguir)
    )

    # Un suscriptor lee el primer evento y se va (cliente que cierra la pestaña).
    stream = turno.subscribe()
    await arranco.wait()
    assert (await anext(stream)).text == "hola"
    await stream.aclose()

    seguir.set()
    assert turno.task is not None
    await turno.task

    assert [event.text for event in turno.events] == ["hola", " mundo"]
    assert turno.done


@pytest.mark.asyncio
async def test_resubscribing_replays_from_the_start(registro: TurnRegistry) -> None:
    """Reenganche sin cursor: el cliente reconstruye el mensaje entero."""
    settings = _settings(1)
    arranco, seguir = asyncio.Event(), asyncio.Event()
    turno = await registro.start(
        settings, uuid4(), _productor_controlado(arranco, seguir)
    )
    await arranco.wait()

    seguir.set()
    assert turno.task is not None
    await turno.task

    recibidos = [event.text async for event in turno.subscribe()]

    assert recibidos == ["hola", " mundo"]


@pytest.mark.asyncio
async def test_cancel_stops_the_turn(registro: TurnRegistry) -> None:
    settings = _settings(1)
    conversation = uuid4()
    turno = await registro.start(settings, conversation, _nunca_termina)

    assert registro.cancel(conversation) is True
    assert turno.task is not None
    await asyncio.wait([turno.task])

    assert turno.done
    assert registro.active_count() == 0
    # Idempotente: volver a detener no explota ni miente.
    assert registro.cancel(conversation) is False


@pytest.mark.asyncio
async def test_timeout_applies_to_the_task(registro: TurnRegistry) -> None:
    """El reloj de pared envuelve la tarea, no la conexión."""
    settings = _settings(1, timeout=0.05)
    conversation = uuid4()
    turno = await registro.start(settings, conversation, _nunca_termina)

    assert turno.task is not None
    await turno.task

    assert turno.done
    assert registro.running(conversation) is False
    assert registro.active_count() == 0


@pytest.mark.asyncio
async def test_a_failing_producer_frees_the_slot(registro: TurnRegistry) -> None:
    """Si el turno revienta, el cupo tiene que volver igual."""
    settings = _settings(1)

    async def explota(turno: RunningTurn) -> None:
        raise RuntimeError("boom")

    turno = await registro.start(settings, uuid4(), explota)
    assert turno.task is not None
    await turno.task

    assert registro.active_count() == 0
    assert turno.done


@pytest.mark.asyncio
async def test_a_finished_conversation_accepts_a_new_turn(registro: TurnRegistry) -> None:
    settings = _settings(5)
    conversation = uuid4()

    async def corto(turno: RunningTurn) -> None:
        turno.publish(_delta("ok"))

    primero = await registro.start(settings, conversation, corto)
    assert primero.task is not None
    await primero.task

    segundo = await registro.start(settings, conversation, _nunca_termina)

    assert segundo is not primero
    assert registro.running(conversation) is True
    registro.reset_for_tests()
