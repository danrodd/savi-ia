"""El repositorio respeta las claves foráneas, como en Postgres.

El `sessionmaker_` del módulo usa SQLite sin `PRAGMA foreign_keys`: así no
se vio que subir un documento limitado a ciertas bases insertaba el alcance
antes que el documento (500 en Postgres). Acá las FKs están activas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentBlobModel,
    CompanyDocumentChunkModel,
    CompanyDocumentDatabaseModel,
    CompanyDocumentModel,
)
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.erp_databases.infrastructure.persistence import ErpDatabaseModel

from .conftest import make_document


@pytest_asyncio.fixture
async def strict_sessionmaker(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'fk.db').as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                ErpDatabaseModel.__table__,
                CompanyDocumentModel.__table__,
                CompanyDocumentDatabaseModel.__table__,
                CompanyDocumentBlobModel.__table__,
                CompanyDocumentChunkModel.__table__,
            ],
        )
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


async def _database(sessionmaker_: async_sessionmaker[AsyncSession]) -> ErpDatabaseModel:
    database = ErpDatabaseModel(
        id=uuid4(),
        code=f"B{uuid4().hex[:6]}".upper(),
        name=f"Base {uuid4().hex[:6]}",
        host="localhost",
        port=5432,
        database="erp",
        username="postgres",
        password_encrypted="x",
        statement_timeout_ms=60000,
        is_default=False,
        is_active=True,
        credentials_unreadable=False,
    )
    async with sessionmaker_() as session:
        session.add(database)
        await session.commit()
    return database


async def test_a_document_scoped_to_some_databases_is_saved(
    strict_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    uploader = await _database(strict_sessionmaker)
    scoped = await _database(strict_sessionmaker)
    repository = SqlAlchemyDocumentRepository(strict_sessionmaker)
    document = make_document(all_databases=False, database_ids=[scoped.id])
    document.uploaded_by_database_id = uploader.id

    await repository.save(document)

    saved = await repository.get_by_id(document.id)
    assert saved is not None
    assert saved.database_ids == [scoped.id]
