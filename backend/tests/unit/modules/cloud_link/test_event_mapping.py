"""Mapeo de filas a eventos (§4): lista blanca, sin contenido, y cada evento
producido cumple el contrato Pydantic y el JSON Schema."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.chat.infrastructure.llm.tools.knowledge import KNOWLEDGE_TIPOS
from app.modules.cloud_link.application.pseudonymizer import Pseudonymizer
from app.modules.cloud_link.domain.entities import EPOCH, Cursor, SyncEvent
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.cloud_link.infrastructure.contract_v1 import EVENT_MODELS
from app.modules.cloud_link.infrastructure.sources import (
    ConversationSource,
    DatabaseSource,
    FreeQuerySource,
    SessionSource,
    TurnSource,
)
from app.modules.cloud_link.infrastructure.sources.free_query_source import result_code
from app.modules.cloud_link.infrastructure.sources.turn_source import (
    KNOWLEDGE_TIPOS_WHITELIST,
    cost_as_string,
    tokens_from_usage,
    whitelisted_tools,
)

from .contract_files import validate_document
from .support import (
    DB_A,
    DB_B,
    T0,
    FakeClock,
    FakeCloudApi,
    add_conversation,
    add_free_query,
    add_message,
    add_session_token,
)

_START = Cursor(EPOCH, "")
_SECRET_TEXTS = (
    "Contenido que nunca debe viajar",
    "Título con datos sensibles",
    "Juan Pérez",
    "SELECT",
    "clientes",
    "USUARIO.REAL",
    "usuario_secreto",
    "srv-norte.interno.local",
    "erp_norte_fisica",
    "secreta",
)


@pytest.fixture
def services(make_services: Callable[..., CloudLinkServices]) -> CloudLinkServices:
    return make_services(FakeCloudApi())


def _sources(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> tuple[TurnSource, ConversationSource, SessionSource, FreeQuerySource, DatabaseSource]:
    from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider

    provider = PseudonymizerProvider(services.repository)
    return (
        TurnSource(sm, provider),
        ConversationSource(sm, provider),
        SessionSource(sm, provider),
        FreeQuerySource(sm),
        DatabaseSource(sm),
    )


def test_knowledge_whitelist_matches_the_dispatcher_in_chat() -> None:
    assert set(KNOWLEDGE_TIPOS) == KNOWLEDGE_TIPOS_WHITELIST


def test_tokens_come_from_usage_and_missing_is_zero() -> None:
    assert tokens_from_usage(None) == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    assert tokens_from_usage({"input_tokens": 1200, "output_tokens": "340", "x": 5}) == {
        "input_tokens": 1200,
        "output_tokens": 340,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    # Basura en usage: cuenta como 0, no rompe el lote.
    assert tokens_from_usage({"input_tokens": "mucho", "output_tokens": -4})["input_tokens"] == 0
    assert tokens_from_usage({"output_tokens": -4})["output_tokens"] == 0


def test_cost_is_an_exact_decimal_string() -> None:
    assert cost_as_string(Decimal("0.012345")) == "0.012345"
    assert cost_as_string(0.1) == "0.100000"
    assert cost_as_string(None) is None
    assert cost_as_string(Decimal("-1")) is None


def test_tools_only_keep_name_status_and_whitelisted_tipo() -> None:
    tools = whitelisted_tools(
        [
            {
                "id": "t1",
                "name": "consultar_datos",
                "status": "ok",
                "input": {"sql": "SELECT secreto", "tipo": "modulo"},
            },
            {
                "name": "consultar_conocimiento",
                "status": "error",
                "input": {"tipo": "modulo", "query": "pregunta del usuario"},
            },
            {"name": "consultar_conocimiento", "input": {"tipo": "inventado"}},
            {"name": "consultar_libre", "status": "ok", "input": {"user_question": "¿Quién?"}},
            {"status": "ok"},
        ]
    )
    assert tools == [
        {"name": "consultar_datos", "status": "ok"},
        {"name": "consultar_conocimiento", "status": "error", "tipo": "modulo"},
        {"name": "consultar_conocimiento", "status": "unknown"},
        {"name": "consultar_libre", "status": "ok"},
    ]
    assert "SELECT" not in json.dumps(tools)


def test_free_query_result_is_normalised_to_the_contract_pattern() -> None:
    assert result_code("ok") == "ok"
    assert result_code("Rejected By-AST!") == "rejected_by_ast_"
    assert result_code("") == "unknown"


async def test_turn_event_maps_tokens_cost_tools_latency_and_action(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    conversation = await add_conversation(sm, user_id=7, owner=DB_A, queried=DB_B)
    await add_message(sm, conversation, role="user", created_at=T0)
    answer = await add_message(
        sm,
        conversation,
        created_at=T0 + timedelta(milliseconds=4210),
        usage={
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_read_input_tokens": 800,
        },
        cost="0.012345",
        tools=[
            {
                "id": "t1",
                "name": "consultar_datos",
                "status": "ok",
                "input": {"sql": "SELECT secreto FROM clientes"},
            },
            {
                "id": "t2",
                "name": "consultar_conocimiento",
                "status": "ok",
                "input": {"tipo": "faq", "consulta": "texto del usuario"},
            },
        ],
    )

    turn_source = _sources(sm, services)[0]
    [event] = await turn_source.read_batch(_START, 10)

    payload = event.to_payload()
    assert payload["schema"] == "turn/1"
    assert payload["source_id"] == str(answer)
    assert payload["occurred_at"] == "2026-10-14T12:00:04.210000Z"
    data = payload["data"]
    assert data["conversation_ref"] == str(conversation)
    assert data["database_ref"] == str(DB_B)
    assert data["provider"] == "claude" and data["model"] == "claude-sonnet-4-6"
    assert data["finish_reason"] == "complete"
    assert data["input_tokens"] == 1200 and data["output_tokens"] == 340
    assert data["cache_read_input_tokens"] == 800
    assert data["cache_creation_input_tokens"] == 0
    assert data["cost_usd"] == "0.012345"
    assert data["tools"] == [
        {"name": "consultar_datos", "status": "ok"},
        {"name": "consultar_conocimiento", "status": "ok", "tipo": "faq"},
    ]
    assert data["latency_ms"] == 4210
    assert data["action"] == "send"
    # user_ref usa la base de IDENTIDAD del dueño (no la consultada).
    pseudonymizer = Pseudonymizer((await services.repository.get()).pseudonym_key)
    assert data["user_ref"] == pseudonymizer.user_ref(DB_A, 7)
    text = json.dumps(payload, ensure_ascii=False)
    assert not any(secret in text for secret in _SECRET_TEXTS)


async def test_turn_includes_superseded_and_deleted_conversations(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    conversation = await add_conversation(sm)
    first = await add_message(sm, conversation, created_at=T0)
    await add_message(sm, conversation, created_at=T0 + timedelta(seconds=5), message_id=uuid4())
    # El primero quedó superseded por el segundo (regenerar).
    async with sm() as session:
        from sqlalchemy import update

        from app.modules.conversations.infrastructure.persistence.models import (
            ConversationModel,
            MessageModel,
        )

        await session.execute(
            update(MessageModel).where(MessageModel.id == first).values(superseded_at=T0)
        )
        await session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation)
            .values(deleted_at=T0)
        )
        await session.commit()

    events = await _sources(sm, services)[0].read_batch(_START, 10)
    assert len(events) == 2


async def test_turn_action_and_latency_are_inferred_from_the_revision_chain(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    conversation = await add_conversation(sm)
    # 1) envío normal
    user_1 = await add_message(sm, conversation, role="user", created_at=T0)
    old_answer = uuid4()
    new_answer = uuid4()
    await add_message(sm, conversation, created_at=T0 + timedelta(seconds=2), message_id=old_answer)
    # 2) regenerar: el user NO cambió, la respuesta nueva reemplaza a la vieja
    await add_message(
        sm, conversation, created_at=T0 + timedelta(seconds=10), message_id=new_answer
    )
    async with sm() as session:
        from sqlalchemy import update

        from app.modules.conversations.infrastructure.persistence.models import MessageModel

        await session.execute(
            update(MessageModel)
            .where(MessageModel.id == old_answer)
            .values(superseded_by_id=new_answer)
        )
        await session.commit()
    # 3) editar la última: user nuevo que reemplaza a user_1, y respuesta nueva
    user_2 = uuid4()
    edited_answer = uuid4()
    await add_message(
        sm, conversation, role="user", created_at=T0 + timedelta(seconds=20), message_id=user_2
    )
    await add_message(
        sm, conversation, created_at=T0 + timedelta(seconds=25), message_id=edited_answer
    )
    async with sm() as session:
        from sqlalchemy import update

        from app.modules.conversations.infrastructure.persistence.models import MessageModel

        await session.execute(
            update(MessageModel).where(MessageModel.id == user_1).values(superseded_by_id=user_2)
        )
        await session.execute(
            update(MessageModel)
            .where(MessageModel.id == new_answer)
            .values(superseded_by_id=edited_answer)
        )
        await session.commit()

    events = await _sources(sm, services)[0].read_batch(_START, 10)
    by_id = {e.source_id: e.data for e in events}
    assert by_id[str(old_answer)]["action"] == "send"
    assert by_id[str(old_answer)]["latency_ms"] == 2000
    # Regenerada: hay un asistente entre este y el user, así que no hay latencia.
    assert by_id[str(new_answer)]["action"] == "regenerate"
    assert by_id[str(new_answer)]["latency_ms"] is None
    assert by_id[str(edited_answer)]["action"] == "edit_last"
    assert by_id[str(edited_answer)]["latency_ms"] == 5000


async def test_every_stream_event_is_valid_and_leaks_nothing(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices, clock: FakeClock
) -> None:
    conversation = await add_conversation(sm)
    await add_message(sm, conversation, role="user")
    await add_message(
        sm,
        conversation,
        created_at=T0 + timedelta(seconds=3),
        usage={"input_tokens": 10},
        cost="0.5",
        tools=[{"name": "consultar_libre", "status": "ok", "input": {"sql": "SELECT 1"}}],
    )
    await add_session_token(sm)
    await add_free_query(sm, conversation_id=conversation, result="rejected_ast")

    turn, conv, session, free_query, database = _sources(sm, services)
    collected: list[SyncEvent] = []
    for source in (turn, conv, session, free_query):
        batch = await source.read_batch(_START, 10)
        assert batch, source.stream
        collected += batch
    collected += await database.snapshot(clock())

    assert {e.schema for e in collected} == set(EVENT_MODELS)
    for event in collected:
        payload = event.to_payload()
        EVENT_MODELS[event.schema].model_validate(payload)
        validate_document(event.schema.split("/")[0], payload)
        text = json.dumps(payload, ensure_ascii=False)
        leaked = [s for s in _SECRET_TEXTS if s in text]
        assert not leaked, f"{event.schema} filtró {leaked}"


async def test_database_snapshot_has_labels_but_never_connection_details(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices, clock: FakeClock
) -> None:
    events = await _sources(sm, services)[4].snapshot(clock())
    assert len(events) == 2
    by_ref = {e.data["database_ref"]: e for e in events}
    norte = by_ref[str(DB_A)]
    assert norte.data["code"] == "NORTE" and norte.data["name"] == "Sede Norte"
    assert norte.data["is_active"] is True and norte.data["is_usable"] is True
    assert norte.source_id == f"{DB_A}:2026-10-14"
    assert set(norte.data) == {
        "database_ref",
        "code",
        "name",
        "is_active",
        "is_usable",
        "credentials_unreadable",
        "last_connection_ok_at",
    }
