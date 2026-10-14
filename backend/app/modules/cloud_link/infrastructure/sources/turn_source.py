"""Stream `turn/1`: un turno del asistente (§4.1).

Origen: `messages` con `role = 'assistant'`, incluidos los superseded y los de
conversaciones borradas, con el mismo criterio que `usage_repository` (esos
tokens se pagaron de verdad).

**Lista blanca estricta.** Lo único que sale de `tool_invocations` es `name`,
`status` y, para `consultar_conocimiento`, `input.tipo` si pertenece a la lista
de tipos conocidos. El resto de `input` (SQL, preguntas) nunca se copia. El
texto del mensaje no se selecciona siquiera.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities import Cursor, SyncEvent
from app.modules.cloud_link.domain.interfaces import EventSource
from app.modules.cloud_link.domain.value_objects import SyncStream
from app.modules.cloud_link.infrastructure.sources.keyset import keyset_after
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)

_ASSISTANT_ROLE = "assistant"
_USER_ROLE = "user"
_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
_KNOWLEDGE_TOOL = "consultar_conocimiento"
# Copia de `KNOWLEDGE_TIPOS` (chat/.../tools/knowledge.py). Se duplica a
# propósito: el extractor no importa la capa de LLM del chat. Un test compara
# las dos listas para que no se desvíen.
KNOWLEDGE_TIPOS_WHITELIST: frozenset[str] = frozenset(
    {
        "intencion",
        "modulo",
        "workflow",
        "faq",
        "glosario",
        "modulos_disponibles",
        "formulario",
        "documentos",
        "documentos_disponibles",
    }
)
_MAX_TOOLS = 100
_COST_QUANTUM = Decimal("0.000001")
_COST_MAX = Decimal("999999.999999")


def tokens_from_usage(usage: dict[str, Any] | None) -> dict[str, int]:
    """Cuatro contadores desde `messages.usage`; lo que falta o no es un
    entero válido cuenta como 0 (igual que `usage_repository`)."""
    counters: dict[str, int] = {}
    for name in _TOKEN_FIELDS:
        raw = (usage or {}).get(name)
        value = 0
        if isinstance(raw, bool):
            value = 0
        elif isinstance(raw, int):
            value = raw
        elif isinstance(raw, float):
            value = int(raw)
        elif isinstance(raw, str):
            try:
                value = int(raw)
            except ValueError:
                value = 0
        counters[name] = max(value, 0)
    return counters


def cost_as_string(cost: Decimal | float | int | str | None) -> str | None:
    """`cost_usd` como texto decimal exacto (6 decimales), nunca float."""
    if cost is None:
        return None
    try:
        value = Decimal(str(cost)).quantize(_COST_QUANTUM)
    except (InvalidOperation, ValueError):
        return None
    if value < 0 or value > _COST_MAX:
        return None
    return format(value, "f")


def whitelisted_tools(invocations: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    tools: list[dict[str, str]] = []
    for item in invocations or []:
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        status = item.get("status")
        entry: dict[str, str] = {
            "name": raw_name.strip()[:100],
            "status": (status.strip() if isinstance(status, str) and status.strip() else "unknown")[
                :32
            ],
        }
        if raw_name == _KNOWLEDGE_TOOL:
            tool_input: Any = item.get("input")
            tipo: Any = (
                cast(dict[str, Any], tool_input).get("tipo")
                if isinstance(tool_input, dict)
                else None
            )
            if isinstance(tipo, str) and tipo in KNOWLEDGE_TIPOS_WHITELIST:
                entry["tipo"] = tipo
        tools.append(entry)
        if len(tools) >= _MAX_TOOLS:
            break
    return tools


def _infer_action(
    *,
    predecessor_at: datetime | None,
    previous_id: UUID | None,
    previous_role: str | None,
    previous_at: datetime | None,
    previous_was_replaced: bool,
) -> str | None:
    """`send`, `edit_last` o `regenerate`, inferido de `superseded_by_id`.

    Un asistente que reemplaza a otro viene de un `regenerate` o de un
    `edit_last`. Si el asistente reemplazado es POSTERIOR al user que lo
    precede, el user no cambió: fue regenerar. Si es anterior, el user es una
    edición. Sin asistente reemplazado, es un envío salvo que el user sea una
    edición de otro (se editó con la última pregunta sin respuesta).
    """
    if previous_id is None:
        return None
    previous_is_user = previous_role == _USER_ROLE
    if predecessor_at is not None:
        if previous_is_user and previous_at is not None and predecessor_at < previous_at:
            return "edit_last"
        return "regenerate"
    if previous_is_user and previous_was_replaced:
        return "edit_last"
    return "send"


class TurnSource(EventSource):
    stream = SyncStream.TURN

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], pseudonymizers: PseudonymizerProvider
    ) -> None:
        self._sessionmaker = sessionmaker
        self._pseudonymizers = pseudonymizers

    async def read_batch(self, after: Cursor, limit: int) -> list[SyncEvent]:
        message = MessageModel
        previous = aliased(MessageModel)
        predecessor = aliased(MessageModel)

        before_this = (
            previous.conversation_id == message.conversation_id,
            previous.id != message.id,
            previous.created_at <= message.created_at,
        )

        def _previous(column: Any) -> Any:
            return (
                select(column)
                .where(*before_this)
                .order_by(previous.created_at.desc(), previous.id.desc())
                .limit(1)
                .correlate(message)
                .scalar_subquery()
            )

        replaced_at = (
            select(predecessor.created_at)
            .where(predecessor.superseded_by_id == message.id, predecessor.role == _ASSISTANT_ROLE)
            .limit(1)
            .correlate(message)
            .scalar_subquery()
        )

        statement = (
            select(
                message.id,
                message.created_at,
                message.conversation_id,
                message.provider,
                message.model,
                message.finish_reason,
                message.usage,
                message.cost_usd,
                message.tool_invocations,
                ConversationModel.erp_database_id,
                ConversationModel.owner_erp_database_id,
                ConversationModel.user_id,
                _previous(previous.id).label("previous_id"),
                _previous(previous.role).label("previous_role"),
                _previous(previous.created_at).label("previous_at"),
                replaced_at.label("predecessor_at"),
            )
            .join(ConversationModel, ConversationModel.id == message.conversation_id)
            .where(
                message.role == _ASSISTANT_ROLE, keyset_after(message.created_at, message.id, after)
            )
            .order_by(message.created_at, message.id)
            .limit(limit)
        )

        pseudonymizer = await self._pseudonymizers.get()
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement)).all()
            previous_ids = {r.previous_id for r in rows if r.previous_id is not None}
            replaced: set[UUID] = set()
            if previous_ids:
                found = (
                    await session.execute(
                        select(MessageModel.superseded_by_id).where(
                            MessageModel.superseded_by_id.in_(previous_ids)
                        )
                    )
                ).scalars()
                replaced = {value for value in found if value is not None}

        events: list[SyncEvent] = []
        for r in rows:
            previous_user = r.previous_role == _USER_ROLE and r.previous_at is not None
            latency: int | None = None
            if previous_user:
                latency = max(int((r.created_at - r.previous_at).total_seconds() * 1000), 0)
            data: dict[str, Any] = {
                "conversation_ref": str(r.conversation_id),
                "database_ref": str(r.erp_database_id) if r.erp_database_id else None,
                "user_ref": pseudonymizer.user_ref(r.owner_erp_database_id, r.user_id),
                "provider": r.provider,
                "model": r.model,
                "finish_reason": r.finish_reason,
                **tokens_from_usage(r.usage),
                "cost_usd": cost_as_string(r.cost_usd),
                "tools": whitelisted_tools(r.tool_invocations),
                "latency_ms": latency,
                "action": _infer_action(
                    predecessor_at=r.predecessor_at,
                    previous_id=r.previous_id,
                    previous_role=r.previous_role,
                    previous_at=r.previous_at,
                    previous_was_replaced=r.previous_id in replaced,
                ),
            }
            events.append(
                SyncEvent(
                    schema=SyncStream.TURN.schema,
                    source_id=str(r.id),
                    occurred_at=r.created_at,
                    data=data,
                    cursor_id=str(r.id),
                )
            )
        return events
