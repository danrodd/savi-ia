"""Scheduler (§5.7) y aislamiento del chat (RNF-05, §8.2)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config import Settings, get_settings
from app.modules.chat.application.requests import ChatAction
from app.modules.chat.application.use_cases import ChatTurnUseCase
from app.modules.chat.domain.entities import ChatEvent, DoneEvent, TextDeltaEvent
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.chat.infrastructure.persistence import (
    ShortLivedConversationRepository,
    SqlAlchemyAssistantMessageWriter,
)
from app.modules.cloud_link.application.use_cases import HeartbeatOutcome
from app.modules.cloud_link.domain.interfaces import SyncLock
from app.modules.cloud_link.domain.value_objects import HistoryMode, LinkStatus
from app.modules.cloud_link.infrastructure import scheduler as scheduler_module
from app.modules.cloud_link.infrastructure.composition import (
    CloudLinkServices,
    build_cloud_link_services,
)
from app.modules.cloud_link.infrastructure.scheduler import CloudLinkScheduler
from app.modules.cloud_link.infrastructure.sync_lock import PostgresAdvisorySyncLock
from app.modules.conversations.domain.entities import Conversation, Message
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)

from .support import (
    CLOUD_URL,
    DB_A,
    FakeCloudApi,
    IngestCall,
    add_conversation,
    add_message,
    hang_forever,
    net_error,
)


async def _link(services: CloudLinkServices) -> None:
    await services.link.execute(
        cloud_url=CLOUD_URL, token="svk_enr_" + "0" * 40, history=HistoryMode.ALL
    )


# ── scheduler ─────────────────────────────────────────────────────────────


async def test_a_crashing_cycle_is_logged_and_the_loop_keeps_going(
    make_services: Callable[..., CloudLinkServices],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(scheduler_module, "CRASH_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(scheduler_module, "IDLE_POLL_SECONDS", 0.0)
    monkeypatch.setattr(scheduler_module, "MIN_WAIT_SECONDS", 0.01)
    services = make_services(FakeCloudApi())
    calls = 0
    recovered = asyncio.Event()

    async def flaky() -> HeartbeatOutcome:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("falla inesperada")
        if calls >= 3:
            recovered.set()
        return HeartbeatOutcome(sent=False)

    monkeypatch.setattr(services.heartbeat, "execute", flaky)
    scheduler = CloudLinkScheduler(services)

    with caplog.at_level(logging.ERROR):
        scheduler.start()
        await asyncio.wait_for(recovered.wait(), timeout=5)
        await scheduler.stop()

    assert calls >= 3
    assert any("falla inesperada" in (r.exc_text or "") for r in caplog.records)


class _Busy(SyncLock):
    """Otro proceso tiene el lock."""

    def acquire(self) -> AbstractAsyncContextManager[bool]:
        return self._cm()

    @asynccontextmanager
    async def _cm(self) -> AsyncGenerator[bool]:
        yield False


async def test_a_cycle_is_skipped_when_another_process_holds_the_lock(
    sm: async_sessionmaker[AsyncSession], make_settings: Callable[..., Settings]
) -> None:
    api = FakeCloudApi()
    services = build_cloud_link_services(
        settings=make_settings(), sessionmaker=sm, cloud_api=api, sync_lock=_Busy()
    )
    await _link(services)
    conversation = await add_conversation(sm)
    await add_message(sm, conversation)

    delay = await CloudLinkScheduler(services).sync_once()

    assert api.ingests == []
    assert delay == 300.0
    assert await services.run_sync_cycle() is False


async def test_two_concurrent_cycles_on_postgres_only_one_sends() -> None:
    """Requiere un Postgres alcanzable con los datos de `.env` (se salta si no)."""
    settings = get_settings().model_copy(update={"agent_db_engine": "postgresql"})
    try:
        engine = create_async_engine(settings.agent_db_url)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"No hay Postgres alcanzable: {error}")

    lock = PostgresAdvisorySyncLock(engine)
    sent: list[str] = []
    inside = asyncio.Event()
    release = asyncio.Event()

    async def cycle(name: str) -> None:
        async with lock.acquire() as acquired:
            if not acquired:
                return
            sent.append(name)
            inside.set()
            await release.wait()

    try:
        first = asyncio.create_task(cycle("a"))
        await asyncio.wait_for(inside.wait(), timeout=10)
        await cycle("b")  # mientras "a" retiene el lock
        release.set()
        await first
        assert sent == ["a"]
        # Soltado el lock, el siguiente ciclo sí puede.
        await cycle("c")
        assert sent == ["a", "c"]
    finally:
        await engine.dispose()


# ── aislamiento del chat ──────────────────────────────────────────────────


class _Runner:
    async def stream_turn(self, prompt: str, **_: Any) -> AsyncIterator[ChatEvent]:
        yield TextDeltaEvent(text="Respuesta del asistente.")
        yield DoneEvent()


class _Titles:
    async def update_from_user(self, conversation_id: UUID, text: str) -> str | None:
        return None

    async def update_from_turn(
        self, conversation_id: UUID, user: str, assistant: str
    ) -> str | None:
        return None


class _ChatWorld:
    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        self.sm = sm
        self.repository = ShortLivedConversationRepository(sm)
        self.owner = ConversationOwner(user_id=7, erp_database_id=DB_A)
        self.use_case = ChatTurnUseCase(
            self.repository,
            cast(LLMRunner, _Runner()),
            cast(AssistantMessageWriter, SqlAlchemyAssistantMessageWriter(sm)),
            cast(ConversationTitleUpdater, _Titles()),
            Settings(title_phase2_timeout_s=0.01),
        )

    async def new_turn(self) -> tuple[list[str], list[tuple[str, str]], float]:
        async with self.sm() as session:
            saved = await SqlAlchemyConversationRepository(session).save(
                Conversation(user_id=7, erp_database_id=DB_A, owner_erp_database_id=DB_A)
            )
            await session.commit()
        started = time.perf_counter()
        await self.use_case.validate(
            saved.id, ChatAction.SEND, expected_owner=self.owner, attachment_ids=[]
        )
        events = [
            type(e).__name__
            async for e in self.use_case.execute(
                saved.id, ChatAction.SEND, "¿Cuánto vendimos hoy?", attachment_ids=[]
            )
        ]
        await asyncio.sleep(0.05)  # el writer del asistente corre en una tarea aparte
        elapsed = time.perf_counter() - started
        messages: Sequence[Message] = await self.repository.list_messages(saved.id)
        return events, [(m.role.value, m.content) for m in messages], elapsed


@pytest.mark.parametrize("failure", ["hangs", "raises"])
async def test_chat_turn_is_unaffected_by_a_cloud_that_hangs_or_fails(
    sm: async_sessionmaker[AsyncSession],
    make_services: Callable[..., CloudLinkServices],
    failure: str,
) -> None:
    world = _ChatWorld(sm)
    baseline_events, baseline_messages, baseline_time = await world.new_turn()

    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    conversation = await add_conversation(sm)
    await add_message(sm, conversation)
    if failure == "hangs":

        async def hang(_: IngestCall) -> None:
            await hang_forever()

        api.ingest_hook = hang
        api.heartbeat_hook = hang_forever
    else:
        api.heartbeat_error = net_error()
        api.ingest_errors = {n: net_error() for n in range(1, 50)}

    scheduler = CloudLinkScheduler(services)
    scheduler.start()
    try:
        await asyncio.sleep(0.2)  # los dos bucles ya están corriendo (o colgados)
        events, messages, elapsed = await asyncio.wait_for(world.new_turn(), timeout=10)
    finally:
        await asyncio.wait_for(scheduler.stop(), timeout=5)

    assert events == baseline_events
    assert messages == baseline_messages
    # Misma duración que sin sincronizador (con margen de ruido de CI).
    assert elapsed < baseline_time + 1.0
    state = await services.repository.get()
    assert state.status in (LinkStatus.LINKED, LinkStatus.OFFLINE)
    if failure == "hangs":
        assert api.attempts >= 1, "el ciclo de envío sí intentó enviar"
