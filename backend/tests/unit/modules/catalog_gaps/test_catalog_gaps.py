"""Vacíos del catálogo: lo que el administrador revisa cada mes para sumar al catálogo.

Fase 4 de la cobertura del ERP. Las señales son locales (las preguntas no salen
de la instalación): consultas libres, consultas fallidas y turnos que llegaron
al tope de consultas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.catalog_gaps.application.build_report import question_key
from app.modules.catalog_gaps.application.csv_export import build_gaps_csv
from app.modules.catalog_gaps.application.use_cases import GetCatalogGapsUseCase
from app.modules.catalog_gaps.domain.value_objects import GapKind
from app.modules.catalog_gaps.infrastructure.http.routes import period
from app.modules.catalog_gaps.infrastructure.sqlalchemy_gap_reader import (
    SqlAlchemyGapEventReader,
    hit_query_limit,
)
from app.modules.conversations.infrastructure.persistence.models.conversation_model import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.modules.free_query.infrastructure.models import AuditQueryModel
from app.shared.exceptions import ValidationError

_MINE = UUID("22222222-2222-2222-2222-222222222222")
_OTHER = UUID("33333333-3333-3333-3333-333333333333")
_NOW = datetime.now(UTC)
_START = _NOW - timedelta(days=30)
_END = _NOW + timedelta(minutes=1)
_LIMIT = 3

_PLAN = 'SELECT codigo FROM "Contabilidad"."PlanContable"'
_SCHEMA = "SELECT column_name FROM information_schema.columns WHERE table_name = 'PlanContable'"


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'g.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as s:
        for db, code in ((_MINE, "MIA"), (_OTHER, "OTRA")):
            s.add(
                ErpDatabaseModel(
                    id=db,
                    code=code,
                    name=code,
                    host="h",
                    port=5432,
                    database=code,
                    username="u",
                    password_encrypted="x",
                )
            )
        await s.commit()
        yield s
    await engine.dispose()


def _conversation(s: AsyncSession, db: UUID, *, deleted: bool = False) -> UUID:
    conversation_id = uuid4()
    s.add(
        ConversationModel(
            id=conversation_id,
            user_id=7,
            title="t",
            erp_database_id=db,
            owner_erp_database_id=db,
            deleted_at=_NOW if deleted else None,
        )
    )
    return conversation_id


def _user(s: AsyncSession, conversation_id: UUID, text: str, minutes_ago: int) -> None:
    s.add(
        MessageModel(
            id=uuid4(),
            conversation_id=conversation_id,
            role="user",
            content=text,
            created_at=_NOW - timedelta(minutes=minutes_ago),
        )
    )


def _assistant(
    s: AsyncSession, conversation_id: UUID, tools: list[dict[str, Any]], minutes_ago: int
) -> None:
    s.add(
        MessageModel(
            id=uuid4(),
            conversation_id=conversation_id,
            role="assistant",
            content="respuesta",
            finish_reason="complete",
            tool_invocations=tools,
            created_at=_NOW - timedelta(minutes=minutes_ago),
        )
    )


def _audit(s: AsyncSession, conversation_id: UUID, sql: str, result: str, minutes_ago: int) -> None:
    s.add(
        AuditQueryModel(
            conversation_id=conversation_id,
            erp_database_id=_MINE,
            user_question="paráfrasis del modelo",
            sql=sql,
            result=result,
            created_at=_NOW - timedelta(minutes=minutes_ago),
        )
    )


def _libre(sql: str, status: str = "ok") -> dict[str, Any]:
    return {"id": str(uuid4()), "name": "consultar_libre", "input": {"sql": sql}, "status": status}


async def _report(session: AsyncSession):  # noqa: ANN202 — el tipo es el del caso de uso
    use_case = GetCatalogGapsUseCase(SqlAlchemyGapEventReader(session), query_limit=_LIMIT)
    return await use_case.execute(_MINE, _START, _END)


async def test_free_queries_are_grouped_by_the_users_own_question(session: AsyncSession) -> None:
    first = _conversation(session, _MINE)
    second = _conversation(session, _MINE)
    await session.flush()
    _user(session, first, "¿Me das el plan de cuentas?", 20)
    _audit(session, first, _SCHEMA, "ok", 19)  # buscar columnas no es un vacío
    _audit(session, first, _PLAN, "ok", 18)
    _audit(session, first, _PLAN + " LIMIT 10", "ok", 17)  # mismo turno: una vez
    _user(session, second, "me das el plan de cuentas", 10)
    _audit(session, second, _PLAN, "ok", 9)
    await session.commit()

    report = await _report(session)

    assert len(report.gaps) == 1
    gap = report.gaps[0]
    assert gap.question == "me das el plan de cuentas"  # la más reciente, tal como se escribió
    assert gap.times == 2
    assert gap.kinds == (GapKind.FREE_QUERY,)
    assert gap.tables == ("Contabilidad.PlanContable",)
    assert report.totals[GapKind.FREE_QUERY] == 2
    assert [(t.table, t.times) for t in report.top_tables] == [("Contabilidad.PlanContable", 2)]


async def test_failed_queries_and_query_limit_are_their_own_kinds(session: AsyncSession) -> None:
    conversation = _conversation(session, _MINE)
    await session.flush()
    _user(session, conversation, "Agrégale la retención en la fuente", 30)
    _audit(session, conversation, 'SELECT x FROM "CuentaPagar"."Nope"', "db_error", 29)
    capped = [_libre(_SCHEMA)] + [_libre(_PLAN)] * _LIMIT + [_libre(_PLAN, "error")]
    _assistant(session, conversation, capped, 28)
    await session.commit()

    report = await _report(session)

    gap = report.gaps[0]
    assert gap.question == "Agrégale la retención en la fuente"
    assert gap.kinds == (GapKind.FAILED_QUERY, GapKind.QUERY_LIMIT)
    assert set(gap.tables) == {"CuentaPagar.Nope", "Contabilidad.PlanContable"}
    assert report.totals == {
        GapKind.FREE_QUERY: 0,
        GapKind.FAILED_QUERY: 1,
        GapKind.QUERY_LIMIT: 1,
    }


async def test_other_databases_and_deleted_conversations_stay_out(session: AsyncSession) -> None:
    other = _conversation(session, _OTHER)
    deleted = _conversation(session, _MINE, deleted=True)
    await session.flush()
    for conversation in (other, deleted):
        _user(session, conversation, "pregunta ajena", 5)
        _audit(session, conversation, _PLAN, "ok", 4)
    await session.commit()

    report = await _report(session)

    assert report.gaps == ()


def test_a_turn_hit_the_limit_when_it_passed_the_cap_and_the_last_was_refused() -> None:
    assert hit_query_limit([_libre(_PLAN)] * _LIMIT + [_libre(_PLAN, "error")], _LIMIT)
    # Con la regla anterior las de esquema gastaban el mismo cupo.
    assert hit_query_limit([_libre(_SCHEMA)] * _LIMIT + [_libre(_PLAN, "error")], _LIMIT)
    assert not hit_query_limit([_libre(_PLAN)] * (_LIMIT + 1), _LIMIT)  # ninguna rechazada
    assert not hit_query_limit([_libre(_PLAN), _libre(_PLAN, "error")], _LIMIT)  # SQL con error


def test_questions_are_compared_without_case_accents_spacing_or_punctuation() -> None:
    assert question_key("  ¿Cuánto   vendimos?  ") == question_key("cuánto vendimos")


async def test_the_csv_opens_in_excel_and_is_safe_from_formulas(session: AsyncSession) -> None:
    conversation = _conversation(session, _MINE)
    await session.flush()
    _user(session, conversation, "=SUMA(A1:A9) del plan de cuentas", 5)
    _audit(session, conversation, _PLAN, "ok", 4)
    await session.commit()

    csv = build_gaps_csv(await _report(session)).decode("utf-8")

    assert csv.startswith("﻿Pregunta;Qué pasó;Veces")
    assert "'=SUMA(A1:A9) del plan de cuentas;Resuelta con consulta libre;1" in csv


def test_the_default_period_is_the_last_30_days_and_has_bounds() -> None:
    start, end = period("America/Bogota", None, None, today=date(2026, 11, 25))

    assert (end - start).days == 30
    with pytest.raises(ValidationError):
        period("America/Bogota", date(2026, 11, 25), date(2026, 11, 1))
    with pytest.raises(ValidationError):
        period("America/Bogota", date(2025, 1, 1), date(2026, 11, 1))
