"""Compatibilidad de la BD del agente con SQLite (instalación de escritorio).

Cubre lo que se rompe en silencio al cambiar de dialecto: tipos de
columna portables, timezone en el round-trip de datetimes, foreign keys
(apagadas por default en SQLite) y las expresiones SQL del repositorio
de consumo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence.models import (
    ErpDatabaseModel,
)
from app.modules.usage.domain.value_objects import UsageFilters, UsagePeriod
from app.modules.usage.infrastructure.persistence.repositories.sqlalchemy_usage_repository import (
    SqlAlchemyUsageRepository,
)

_PERIOD = UsagePeriod(
    start=datetime(2026, 1, 1, tzinfo=UTC),
    end=datetime(2027, 1, 1, tzinfo=UTC),
)


@pytest.fixture
async def sqlite_sessionmaker(tmp_path: Path) -> Any:
    """Engine SQLite con los mismos PRAGMA que aplica `pool.py`."""
    db = tmp_path / "savi.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


# Base del ERP de la conversación sembrada. El consumo se agrega por el
# par `(erp_database_id, user_id)`, así que el seed necesita las dos
# mitades de la identidad.
_DATABASE_ID = uuid4()


async def _seed(session: AsyncSession) -> ConversationModel:
    session.add(
        ErpDatabaseModel(
            id=_DATABASE_ID,
            code="TEST",
            name="Cliente de prueba",
            host="localhost",
            port=5432,
            database="erp_test",
            username="postgres",
            password_encrypted="cifrado",
        )
    )
    await session.flush()
    conversation = ConversationModel(
        id=uuid4(),
        user_id=7,
        erp_database_id=_DATABASE_ID,
        owner_erp_database_id=_DATABASE_ID,
        title="Consumo del mes",
    )
    session.add(conversation)
    await session.flush()
    session.add(
        MessageModel(
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content="respuesta",
            usage={"input_tokens": 100, "output_tokens": 40},
            cost_usd=Decimal("0.001234"),
            provider="Claude",
            model="claude-sonnet",
            created_at=datetime(2026, 6, 1, 15, 30, tzinfo=UTC),
        )
    )
    await session.commit()
    return conversation


async def test_uuid_json_and_numeric_roundtrip(sqlite_sessionmaker: Any) -> None:
    """`UuidType`/`JsonType` deben devolver los mismos tipos de Python."""
    async with sqlite_sessionmaker() as session:
        conversation = await _seed(session)

    async with sqlite_sessionmaker() as session:
        message = (await session.execute(select(MessageModel))).scalar_one()
        assert message.conversation_id == conversation.id
        assert message.usage == {"input_tokens": 100, "output_tokens": 40}
        assert message.cost_usd == Decimal("0.001234")


async def test_datetimes_come_back_timezone_aware(sqlite_sessionmaker: Any) -> None:
    """SQLite descarta el offset; `UtcDateTime` tiene que reponerlo.

    Sin esto, comparar `expires_at` contra `datetime.now(UTC)` en el
    refresh de tokens levanta TypeError en producción.
    """
    expires = datetime.now(UTC) + timedelta(days=7)
    async with sqlite_sessionmaker() as session:
        session.add(
            RefreshTokenModel(
                jti=uuid4(), user_id=7, user_login="dora", expires_at=expires
            )
        )
        await session.commit()

    async with sqlite_sessionmaker() as session:
        token = (await session.execute(select(RefreshTokenModel))).scalar_one()
        assert token.expires_at.tzinfo is not None
        assert token.expires_at > datetime.now(UTC)
        # `server_default=func.now()` también tiene que volver aware.
        assert token.created_at.tzinfo is not None


async def test_foreign_key_cascade_is_enforced(sqlite_sessionmaker: Any) -> None:
    """Sin `PRAGMA foreign_keys=ON` el CASCADE no corre y quedan huérfanos."""
    async with sqlite_sessionmaker() as session:
        conversation = await _seed(session)
        await session.delete(conversation)
        await session.commit()

    async with sqlite_sessionmaker() as session:
        remaining = (await session.execute(select(MessageModel))).scalars().all()
        assert remaining == []


async def test_usage_totals_aggregate_json_tokens(sqlite_sessionmaker: Any) -> None:
    """El operador `->>` sobre la columna JSON tiene que sumar en SQLite."""
    async with sqlite_sessionmaker() as session:
        await _seed(session)

    async with sqlite_sessionmaker() as session:
        repo = SqlAlchemyUsageRepository(session, reporting_timezone="America/Bogota")
        totals = await repo.totals_for_user(
            7, _PERIOD, erp_database_id=_DATABASE_ID
        )
        assert totals.input_tokens == 100
        assert totals.output_tokens == 40
        assert totals.message_count == 1


async def test_usage_daily_buckets_by_local_date(sqlite_sessionmaker: Any) -> None:
    """15:30 UTC es el mismo día en Bogotá (UTC-5); 02:00 UTC es el anterior."""
    async with sqlite_sessionmaker() as session:
        await _seed(session)

    async with sqlite_sessionmaker() as session:
        repo = SqlAlchemyUsageRepository(session, reporting_timezone="America/Bogota")
        daily = await repo.daily_for_user(
            7, _PERIOD, erp_database_id=_DATABASE_ID
        )
        assert len(daily) == 1
        assert str(daily[0].day) == "2026-06-01"


async def test_usage_conversation_stats_percentiles(sqlite_sessionmaker: Any) -> None:
    """`percentile_cont` no existe en SQLite: hay que resolverlo aparte."""
    async with sqlite_sessionmaker() as session:
        await _seed(session)

    async with sqlite_sessionmaker() as session:
        repo = SqlAlchemyUsageRepository(session, reporting_timezone="America/Bogota")
        stats = await repo.conversation_stats(_PERIOD)
        assert stats.count == 1
        assert stats.p50_cost_usd == pytest.approx(0.001234)


async def test_usage_filters_provider_and_model_on_all_aggregates(
    sqlite_sessionmaker: Any,
) -> None:
    async with sqlite_sessionmaker() as session:
        await _seed(session)

    async with sqlite_sessionmaker() as session:
        repo = SqlAlchemyUsageRepository(session, reporting_timezone="America/Bogota")
        filters = UsageFilters(provider=" Claude ", model="claude-sonnet")

        assert (await repo.system_totals(_PERIOD, filters=filters)).message_count == 1
        assert len(await repo.daily_system(_PERIOD, filters=filters)) == 1
        assert len(await repo.per_user(_PERIOD, filters=filters)) == 1
        assert (await repo.conversation_stats(_PERIOD, filters=filters)).count == 1
        assert (await repo.user_stats(_PERIOD, filters=filters)).active_count == 1
        assert len(await repo.per_conversation(_PERIOD, limit=10, filters=filters)) == 1

        unknown = UsageFilters(provider="Gemini")
        assert (await repo.system_totals(_PERIOD, filters=unknown)).message_count == 0
        assert await repo.daily_system(_PERIOD, filters=unknown) == []
