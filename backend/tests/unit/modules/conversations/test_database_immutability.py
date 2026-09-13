"""D2: la base de una conversación no cambia una vez creada.

`erp_database_id` (la base CONSULTADA) y `owner_erp_database_id` (la
IDENTIDAD del dueño) se fijan al crear y ningún camino del repositorio
las puede tocar después. Cambiar de cliente es una conversación nueva,
no una edición — si a mitad de un hilo cambiara la base, el LLM
razonaría sobre datos mezclados de dos clientes.

`ConversationRepository` no expone ningún método para cambiar esas dos
columnas: el repositorio tiene `save` (solo inserta), `update_title` y
`soft_delete`. Este test ejercita los dos que sí mutan una conversación
existente y confirma que ninguno las toca, más una verificación de la
interfaz misma para que agregar un método nuevo con ese poder no pase
desapercibido.
"""
from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.conversations.domain.entities import Conversation
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyConversationRepository,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel

_QUERIED = UUID("11111111-1111-1111-1111-111111111111")
_OWNER = UUID("22222222-2222-2222-2222-222222222222")


def _erp_database(database_id: UUID, code: str) -> ErpDatabaseModel:
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


@pytest_asyncio.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'im.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        s.add(_erp_database(_QUERIED, "CONSULTADA"))
        s.add(_erp_database(_OWNER, "IDENTIDAD"))
        await s.commit()
        yield s
    await engine.dispose()


async def _create(repository: SqlAlchemyConversationRepository) -> Conversation:
    return await repository.save(
        Conversation(
            id=uuid4(),
            user_id=1,
            erp_database_id=_QUERIED,
            owner_erp_database_id=_OWNER,
            title="Original",
        )
    )


async def test_renaming_does_not_touch_either_database_column(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyConversationRepository(session)
    conversation = await _create(repository)

    await repository.update_title(
        conversation.id, "Nuevo título", respect_lock=False, lock=True
    )

    reloaded = await repository.get_by_id(conversation.id)
    assert reloaded is not None
    assert reloaded.title == "Nuevo título"
    assert reloaded.erp_database_id == _QUERIED
    assert reloaded.owner_erp_database_id == _OWNER


async def test_soft_delete_does_not_touch_either_database_column(
    session: AsyncSession,
) -> None:
    repository = SqlAlchemyConversationRepository(session)
    conversation = await _create(repository)

    await repository.soft_delete(conversation.id)

    reloaded = await repository.get_by_id(conversation.id)
    assert reloaded is not None
    assert reloaded.is_deleted
    assert reloaded.erp_database_id == _QUERIED
    assert reloaded.owner_erp_database_id == _OWNER


def test_repository_interface_exposes_no_way_to_change_the_database_columns() -> None:
    """Si algún día alguien agrega un parámetro `erp_database_id` u
    `owner_erp_database_id` a un método mutador, este test lo marca —
    para que romper D2 sea una decisión explícita, no un accidente."""
    mutating_methods = ("update_title", "soft_delete", "supersede_messages")
    forbidden = {"erp_database_id", "owner_erp_database_id"}

    for name in mutating_methods:
        params = set(inspect.signature(getattr(ConversationRepository, name)).parameters)
        assert not (params & forbidden), (
            f"{name} no debería poder recibir {params & forbidden}"
        )
