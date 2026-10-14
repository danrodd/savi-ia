"""Ciclo de envío (§5.3, §5.6, §8.2): keyset, relectura, marca, batch_id,
413/422, suspensión, "solo desde hoy" e inventario de bases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cloud_link.domain.value_objects import HistoryMode, LinkStatus, SyncPolicy
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.conversations.infrastructure.persistence.models import MessageModel

from .support import (
    DB_A,
    T0,
    FakeClock,
    FakeCloudApi,
    add_conversation,
    add_message,
    http_error,
    net_error,
)


async def _link(services: CloudLinkServices, history: HistoryMode = HistoryMode.ALL) -> None:
    await services.link.execute(
        cloud_url="https://cloud.example.test", token="svk_enr_" + "0" * 40, history=history
    )


async def _bulk_assistant_messages(
    sm: async_sessionmaker[AsyncSession], count: int, *, created_at: datetime = T0
) -> list[str]:
    """`count` respuestas del asistente con el MISMO `created_at`."""
    conversation = await add_conversation(sm)
    ids = [uuid4() for _ in range(count)]
    async with sm() as session:
        session.add_all(
            MessageModel(
                id=i,
                conversation_id=conversation,
                role="assistant",
                content="x",
                created_at=created_at,
                usage={"input_tokens": 1},
            )
            for i in ids
        )
        await session.commit()
    return [str(i) for i in ids]


async def test_keyset_with_1200_rows_sharing_created_at_sends_3_batches_without_gaps(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    expected = set(await _bulk_assistant_messages(sm, 1200))

    result = await services.sync.execute()

    turn_calls = [c for c in api.ingests if c.events[0]["schema"] == "turn/1"]
    assert [len(c.events) for c in turn_calls] == [500, 500, 200]
    sent = [str(e["source_id"]) for c in turn_calls for e in c.events]
    assert len(sent) == len(set(sent)) == 1200, "hubo repetidos"
    assert set(sent) == expected, "hubo filas salteadas"
    assert len({c.batch_id for c in turn_calls}) == 3
    assert result.ok
    watermark = await services.repository.get_watermark("turn")
    assert watermark is not None and watermark.id == sent[-1]
    assert watermark.last_ok_at == T0


async def test_batch_size_follows_the_policy_from_cloud(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi(policy=SyncPolicy(max_batch_events=100))
    services = make_services(api)
    await _link(services)
    await _bulk_assistant_messages(sm, 250)

    await services.sync.execute()

    turn_calls = [c for c in api.ingests if c.events[0]["schema"] == "turn/1"]
    assert [len(c.events) for c in turn_calls] == [100, 100, 50]


async def test_a_message_inserted_before_the_watermark_is_sent_by_the_next_cycle(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    conversation = await add_conversation(sm)
    first = await add_message(sm, conversation, created_at=T0 + timedelta(minutes=10))
    await services.sync.execute()
    assert str(first) in api.unique_source_ids("turn/1")

    # Un writer confirma, tarde, un mensaje con `created_at` 5 minutos ANTES de
    # la marca que el ciclo anterior ya adelantó.
    late = await add_message(sm, conversation, created_at=T0 + timedelta(minutes=5))
    await services.sync.execute()

    assert str(late) in api.unique_source_ids("turn/1")


async def test_failure_midway_keeps_the_watermark_and_the_retry_reuses_the_batch_id(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi(ingest_errors={2: net_error()})
    services = make_services(api)
    await _link(services)
    expected = set(await _bulk_assistant_messages(sm, 1200))

    first_cycle = await services.sync.execute()

    assert first_cycle.aborted
    # El lote 1 se aceptó; el lote 2 falló: la marca queda al final del 1 y
    # NO pasa de ahí.
    watermark = await services.repository.get_watermark("turn")
    batch_1 = api.ingests[0].events
    assert watermark is not None and watermark.id == batch_1[-1]["source_id"]
    assert watermark.last_ok_at is None  # el stream nunca terminó un ciclo
    state = await services.repository.get()
    assert state.consecutive_failures == 1 and state.last_error_code == "network_error"

    second_cycle = await services.sync.execute()

    failed, retried = api.ingests[1], api.ingests[2]
    assert retried.batch_id == failed.batch_id
    assert retried.events == failed.events
    assert second_cycle.ok
    sent = {str(e["source_id"]) for e in api.events("turn/1")}
    assert sent == expected
    state = await services.repository.get()
    assert state.consecutive_failures == 0 and state.last_error_code is None


async def test_failure_in_the_first_batch_does_not_move_the_watermark(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi(ingest_errors={1: http_error(503, "unavailable")})
    services = make_services(api)
    await _link(services)
    await _bulk_assistant_messages(sm, 10)
    before = await services.repository.get_watermark("turn")

    result = await services.sync.execute()

    assert result.aborted and result.stream_errors == {"turn": "unavailable"}
    assert await services.repository.get_watermark("turn") == before


async def test_413_halves_the_batch_down_to_a_minimum_of_50(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi(ingest_errors={n: http_error(413, "batch_too_large") for n in range(1, 6)})
    services = make_services(api)
    await _link(services)
    await _bulk_assistant_messages(sm, 600)

    result = await services.sync.execute()

    sizes = [len(c.events) for c in api.ingests[:5]]
    assert sizes == [500, 250, 125, 62, 50]
    # Con el mínimo el 413 ya no se puede resolver: queda registrado y la
    # marca no se mueve.
    assert result.stream_errors["turn"] == "batch_too_large"
    state = await services.repository.get()
    assert state.last_error_code == "batch_too_large"

    # El tamaño reducido se conserva para el siguiente ciclo.
    api.ingest_errors.clear()
    before = len(api.ingests)
    await services.sync.execute()
    next_turn = next(c for c in api.ingests[before:] if c.events[0]["schema"] == "turn/1")
    assert len(next_turn.events) == 50


async def test_422_stops_that_stream_only_and_flags_the_contract_error(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi(ingest_errors={1: http_error(422, "invalid_envelope")})
    services = make_services(api)
    await _link(services)
    conversation = await add_conversation(sm)
    await add_message(sm, conversation)

    result = await services.sync.execute()

    state = await services.repository.get()
    assert state.last_error_code == "contract_rejected"
    assert result.stream_errors == {"turn": "invalid_envelope"}
    # El stream del turno no avanzó...
    turn_mark = await services.repository.get_watermark("turn")
    assert turn_mark is not None and turn_mark.id == ""
    # ...pero los demás siguieron.
    assert api.events("conversation/1")
    assert state.status == LinkStatus.LINKED


async def test_a_suspended_instance_that_stores_nothing_does_not_advance_marks(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi(store_nothing=True)
    services = make_services(api)
    await _link(services)
    conversation = await add_conversation(sm)
    await add_message(sm, conversation)

    result = await services.sync.execute()

    assert result.aborted
    for stream in ("turn", "conversation", "session", "free_query"):
        mark = await services.repository.get_watermark(stream)
        assert mark is not None and mark.id == ""

    # Reactivada: se retoma desde donde quedó, sin pérdida.
    api.store_nothing = False
    await services.sync.execute()
    assert len(api.unique_source_ids("turn/1")) == 1


async def test_from_now_sends_nothing_that_existed_before_linking(
    sm: async_sessionmaker[AsyncSession],
    make_services: Callable[..., CloudLinkServices],
    clock: FakeClock,
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    conversation = await add_conversation(sm, created_at=T0 - timedelta(minutes=5))
    # 5 minutos antes del vínculo: dentro de la ventana de relectura de 15.
    await add_message(sm, conversation, created_at=T0 - timedelta(minutes=5))
    await _link(services, HistoryMode.FROM_NOW)

    await services.sync.execute()
    assert api.events("turn/1") == []
    assert api.events("conversation/1") == []

    clock.advance(minutes=1)
    fresh = await add_message(sm, conversation, created_at=clock())
    await services.sync.execute()
    assert api.unique_source_ids("turn/1") == [str(fresh)]


async def test_full_history_starts_from_the_epoch(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    conversation = await add_conversation(sm, created_at=T0 - timedelta(days=400))
    old = await add_message(sm, conversation, created_at=T0 - timedelta(days=400))
    await _link(services, HistoryMode.ALL)

    await services.sync.execute()

    assert str(old) in api.unique_source_ids("turn/1")


async def test_database_inventory_is_sent_on_change_or_after_24_hours(
    sm: async_sessionmaker[AsyncSession],
    make_services: Callable[..., CloudLinkServices],
    clock: FakeClock,
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)

    await services.sync.execute()
    assert len(api.events("database/1")) == 2  # dos sucursales

    clock.advance(minutes=5)
    await services.sync.execute()
    assert len(api.events("database/1")) == 2, "sin cambios no se reenvía"

    # Cambia el inventario: se envía de nuevo.
    async with sm() as session:
        from sqlalchemy import update

        from app.modules.erp_databases.infrastructure.persistence.models import (
            ErpDatabaseModel,
        )

        await session.execute(
            update(ErpDatabaseModel).where(ErpDatabaseModel.id == DB_A).values(is_active=False)
        )
        await session.commit()
    clock.advance(minutes=5)
    await services.sync.execute()
    assert len(api.events("database/1")) == 4

    # Pasadas 24 horas se reenvía aunque no cambie.
    clock.advance(hours=25)
    await services.sync.execute()
    assert len(api.events("database/1")) == 6


async def test_cycle_is_skipped_when_cloud_disables_sync_or_not_linked(
    make_services: Callable[..., CloudLinkServices],
) -> None:
    api = FakeCloudApi()
    services = make_services(api)

    assert (await services.sync.execute()).skipped_reason == "not_syncing"

    api.policy = SyncPolicy(sync_enabled=False)
    await _link(services)
    assert (await services.sync.execute()).skipped_reason == "sync_disabled_by_cloud"
    assert api.ingests == []


async def test_preview_shows_exactly_the_first_event_the_cycle_would_send(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    from .support import add_free_query, add_session_token

    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    conversation = await add_conversation(sm)
    await add_message(sm, conversation, role="user")
    await add_message(
        sm,
        conversation,
        created_at=T0 + timedelta(seconds=3),
        usage={"input_tokens": 7},
        cost="0.25",
    )
    await add_session_token(sm)
    await add_free_query(sm, conversation_id=conversation)

    preview = await services.preview.execute()
    await services.sync.execute()

    for stream, schema in (
        ("turn", "turn/1"),
        ("conversation", "conversation/1"),
        ("session", "session/1"),
        ("free_query", "free_query/1"),
        ("database", "database/1"),
    ):
        shipped = api.events(schema)[0]
        assert preview.events[stream] == shipped, stream
    assert preview.heartbeat["deployment_mode"] == "desktop"
    assert "pseudonym" not in str(preview.heartbeat)
