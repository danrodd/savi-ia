"""Aislamiento de identidad entre bases de clientes.

Es el test más importante de todo el requerimiento. Cubre el defecto que
se activaría al registrar el segundo cliente: el `idUsuario` del ERP se
repite entre bases, así que el usuario 5 del cliente A y el 5 del cliente
B son personas distintas que el código anterior trataba como la misma.

Todos los escenarios usan **el mismo `user_id` en dos bases**, que es
exactamente la colisión que hay que impedir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.modules.usage.domain.value_objects import UsagePeriod
from app.modules.usage.infrastructure.persistence.repositories.sqlalchemy_usage_repository import (  # noqa: E501
    SqlAlchemyUsageRepository,
)

# La colisión: el MISMO idUsuario en dos clientes distintos.
_SHARED_USER_ID = 5

_DATABASE_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DATABASE_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_PERIOD = UsagePeriod(
    start=datetime(2026, 6, 1, tzinfo=UTC),
    end=datetime(2026, 7, 1, tzinfo=UTC),
)


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'i.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        await _seed(s)
        yield s
    await engine.dispose()


def _database(database_id: UUID, code: str) -> ErpDatabaseModel:
    return ErpDatabaseModel(
        id=database_id,
        code=code,
        name=f"Cliente {code}",
        host="localhost",
        port=5432,
        database=f"erp_{code.lower()}",
        username="postgres",
        password_encrypted="cifrado",
    )


async def _seed(session: AsyncSession) -> None:
    """Dos clientes, cada uno con una conversación del `idUsuario` 5."""
    session.add(_database(_DATABASE_A, "NORTE"))
    session.add(_database(_DATABASE_B, "SUR"))
    await session.flush()

    for database_id, title, tokens in (
        (_DATABASE_A, "Hilo del cliente A", 100),
        (_DATABASE_B, "Hilo del cliente B", 700),
    ):
        conversation = ConversationModel(
            id=uuid4(),
            user_id=_SHARED_USER_ID,
            erp_database_id=database_id,
            owner_erp_database_id=database_id,
            title=title,
        )
        session.add(conversation)
        await session.flush()
        session.add(
            MessageModel(
                id=uuid4(),
                conversation_id=conversation.id,
                role="assistant",
                content="respuesta",
                usage={"input_tokens": tokens, "output_tokens": 0},
                cost_usd=Decimal("1.000000"),
                created_at=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
            )
        )
    await session.commit()


# ── Listado de conversaciones ────────────────────────────────────────


async def test_user_only_sees_conversations_of_their_own_client(
    session: AsyncSession,
) -> None:
    """El escenario exacto del defecto: sin el scope por base, el usuario
    5 del cliente B vería el hilo del usuario 5 del cliente A."""
    repository = SqlAlchemyConversationRepository(session)

    from_a = await repository.list_for_user(_SHARED_USER_ID, owner_erp_database_id=_DATABASE_A)
    from_b = await repository.list_for_user(_SHARED_USER_ID, owner_erp_database_id=_DATABASE_B)

    assert [c.title for c in from_a] == ["Hilo del cliente A"]
    assert [c.title for c in from_b] == ["Hilo del cliente B"]


# ── Verificación de propiedad ────────────────────────────────────────


async def test_owner_of_other_client_cannot_open_the_conversation(
    session: AsyncSession,
) -> None:
    """404, no 403: no le confirmamos al atacante que la conversación
    existe."""
    repository = SqlAlchemyConversationRepository(session)
    from app.modules.conversations.application.use_cases import (
        GetConversationWithMessagesUseCase,
    )

    conversation_a = (
        await repository.list_for_user(_SHARED_USER_ID, owner_erp_database_id=_DATABASE_A)
    )[0]
    use_case = GetConversationWithMessagesUseCase(repository)

    # El mismo idUsuario, pero del otro cliente.
    intruder = ConversationOwner(user_id=_SHARED_USER_ID, erp_database_id=_DATABASE_B)
    with pytest.raises(ConversationNotFoundError):
        await use_case.execute(conversation_a.id, expected_owner=intruder)

    # Y el dueño real sí la abre.
    owner = ConversationOwner(user_id=_SHARED_USER_ID, erp_database_id=_DATABASE_A)
    result = await use_case.execute(conversation_a.id, expected_owner=owner)
    assert result.conversation.title == "Hilo del cliente A"


def test_legacy_conversation_without_database_belongs_to_nobody() -> None:
    """Una conversación anterior al multi-BD no se puede atribuir.

    Queda invisible en vez de accesible por la persona equivocada:
    asumir que era de la base actual es justo el cruce que se evita.
    """
    owner = ConversationOwner(user_id=_SHARED_USER_ID, erp_database_id=_DATABASE_A)

    assert owner.owns(_SHARED_USER_ID, None) is False
    assert owner.owns(None, _DATABASE_A) is False
    assert owner.owns(_SHARED_USER_ID, _DATABASE_A) is True


# ── Identidad vs. base consultada (D10) ─────────────────────────────


async def test_conversation_visible_and_ownable_across_queried_databases(
    session: AsyncSession,
) -> None:
    """El escenario de D10: una identidad abre una conversación contra UN
    cliente y otra contra OTRO, sin cambiar de sesión.

    `erp_database_id` (consultada) y `owner_erp_database_id` (identidad)
    quedan distintos a propósito. Antes de separarlos, el listado y el
    ownership comparaban la identidad contra la base consultada y la
    conversación quedaba invisible/inaccesible para su propio dueño.
    """
    repository = SqlAlchemyConversationRepository(session)
    from app.modules.conversations.application.use_cases import (
        GetConversationWithMessagesUseCase,
    )

    cross = ConversationModel(
        id=uuid4(),
        user_id=_SHARED_USER_ID,
        erp_database_id=_DATABASE_B,  # consulta al cliente B...
        owner_erp_database_id=_DATABASE_A,  # ...con la identidad del cliente A.
        title="Hilo cruzado",
    )
    session.add(cross)
    await session.commit()

    listed = await repository.list_for_user(_SHARED_USER_ID, owner_erp_database_id=_DATABASE_A)
    assert "Hilo cruzado" in [c.title for c in listed]

    owner = ConversationOwner(user_id=_SHARED_USER_ID, erp_database_id=_DATABASE_A)
    use_case = GetConversationWithMessagesUseCase(repository)
    result = await use_case.execute(cross.id, expected_owner=owner)
    assert result.conversation.title == "Hilo cruzado"
    assert result.conversation.erp_database_id == _DATABASE_B


# ── Consumo ──────────────────────────────────────────────────────────


async def test_usage_does_not_add_up_across_clients(session: AsyncSession) -> None:
    """Sin el scope, el consumo del usuario 5 sumaría 800 tokens (los dos
    clientes) en vez de los 100 que gastó en el cliente A."""
    repository = SqlAlchemyUsageRepository(session, reporting_timezone="UTC")

    totals_a = await repository.totals_for_user(
        _SHARED_USER_ID, _PERIOD, erp_database_id=_DATABASE_A
    )
    totals_b = await repository.totals_for_user(
        _SHARED_USER_ID, _PERIOD, erp_database_id=_DATABASE_B
    )

    assert totals_a.input_tokens == 100
    assert totals_b.input_tokens == 700


async def test_per_user_ranking_does_not_merge_homonyms(
    session: AsyncSession,
) -> None:
    """El ranking global agrupa por el par, no por el entero: si no, los
    dos usuarios 5 aparecerían como una sola persona."""
    repository = SqlAlchemyUsageRepository(session, reporting_timezone="UTC")

    rows = await repository.per_user(_PERIOD)

    assert len(rows) == 2
    assert {r.erp_database_id for r in rows} == {_DATABASE_A, _DATABASE_B}
    assert all(r.user_id == _SHARED_USER_ID for r in rows)


async def _add_cross_conversation(session: AsyncSession, tokens: int) -> None:
    """El usuario 5 del cliente A (soporte) consulta al cliente B."""
    cross = ConversationModel(
        id=uuid4(),
        user_id=_SHARED_USER_ID,
        erp_database_id=_DATABASE_B,
        owner_erp_database_id=_DATABASE_A,
        title="Soporte atendiendo al cliente B",
    )
    session.add(cross)
    await session.flush()
    session.add(
        MessageModel(
            id=uuid4(),
            conversation_id=cross.id,
            role="assistant",
            content="respuesta",
            usage={"input_tokens": tokens, "output_tokens": 0},
            cost_usd=Decimal("1.000000"),
            created_at=datetime(2026, 6, 15, 13, 0, tzinfo=UTC),
        )
    )
    await session.commit()


async def test_per_user_ranking_attributes_cross_queries_to_the_login_identity(
    session: AsyncSession,
) -> None:
    """Lo que el usuario 5 de A gastó consultando a B es de él, no del
    usuario 5 de B.

    El ranking agrupaba por la base CONSULTADA: los 30 tokens del hilo
    cruzado terminaban sumados a la otra persona.
    """
    await _add_cross_conversation(session, tokens=30)
    repository = SqlAlchemyUsageRepository(session, reporting_timezone="UTC")

    rows = {r.erp_database_id: r.totals.input_tokens for r in await repository.per_user(_PERIOD)}

    assert rows == {_DATABASE_A: 130, _DATABASE_B: 700}


async def test_active_users_count_homonyms_as_different_people(
    session: AsyncSession,
) -> None:
    """Dos usuarios 5 de clientes distintos son dos usuarios activos."""
    repository = SqlAlchemyUsageRepository(session, reporting_timezone="UTC")

    stats = await repository.user_stats(_PERIOD)

    assert stats.active_count == 2


async def test_usage_per_database_follows_the_queried_client(
    session: AsyncSession,
) -> None:
    """El desglose por base responde "cuánto costó cada cliente": el hilo
    cruzado cuenta para B, que es a quien se atendió."""
    from app.modules.usage.domain.value_objects import UsageFilters

    await _add_cross_conversation(session, tokens=30)
    repository = SqlAlchemyUsageRepository(session, reporting_timezone="UTC")

    rows = {
        r.erp_database_id: r.totals.input_tokens
        for r in await repository.database_totals_system(_PERIOD)
    }
    solo_b = await repository.system_totals(
        _PERIOD, filters=UsageFilters(databases=frozenset({_DATABASE_B}))
    )

    assert rows == {_DATABASE_A: 100, _DATABASE_B: 730}
    assert solo_b.input_tokens == 730
