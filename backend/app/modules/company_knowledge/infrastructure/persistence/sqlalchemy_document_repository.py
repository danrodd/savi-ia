from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    CursorResult,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
    DocumentChunk,
)
from app.modules.company_knowledge.domain.entities.processing import PendingChunk
from app.modules.company_knowledge.domain.interfaces import (
    DocumentRepository,
    ProcessingOutcome,
)
from app.modules.company_knowledge.domain.value_objects import (
    DocumentStatus,
    DocumentStatusCode,
    DocumentVisibility,
)
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentBlobModel,
    CompanyDocumentChunkModel,
    CompanyDocumentDatabaseModel,
    CompanyDocumentModel,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _to_modules(values: Sequence[str]) -> list[ModuleCode]:
    modules: list[ModuleCode] = []
    for value in values:
        try:
            modules.append(ModuleCode(value))
        except ValueError:
            continue
    return modules


def _to_status(value: str) -> DocumentStatus:
    try:
        return DocumentStatus(value)
    except ValueError:
        return DocumentStatus.FAILED


def _to_status_code(value: str | None) -> DocumentStatusCode | None:
    if value is None:
        return None
    try:
        return DocumentStatusCode(value)
    except ValueError:
        return DocumentStatusCode.INTERNAL_ERROR


def _to_visibility(value: str) -> DocumentVisibility:
    try:
        return DocumentVisibility(value)
    except ValueError:
        return DocumentVisibility.ADMINS


def _required_database_id(document: CompanyDocument) -> UUID:
    if document.uploaded_by_database_id is None:
        raise ValueError("`uploaded_by_database_id` es obligatorio.")
    return document.uploaded_by_database_id


class SqlAlchemyDocumentRepository(DocumentRepository):
    """Repositorio con sessionmaker propio: sirve igual al request y al worker."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    # ── Documentos ───────────────────────────────────────────────────────
    async def save(self, document: CompanyDocument) -> CompanyDocument:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyDocumentModel, document.id)
            if model is None:
                session.add(self._to_model(document))
            else:
                self._apply(model, document)
            await self._replace_databases(session, document)
            await session.commit()
        return document

    async def update_access_metadata(self, document: CompanyDocument) -> bool:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyDocumentModel, document.id)
            if model is None or model.deleted_at is not None:
                return False
            model.title = document.title
            model.visibility = document.visibility.value
            model.modules = [module.value for module in document.modules]
            model.all_databases = document.all_databases
            model.updated_at = _now()
            await self._replace_databases(session, document)
            await session.commit()
            return True

    async def get_by_id(self, document_id: UUID) -> CompanyDocument | None:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyDocumentModel, document_id)
            if model is None:
                return None
            database_ids = await self._database_ids(session, document_id)
            return self._to_entity(model, database_ids)

    async def get_by_ids(self, document_ids: Sequence[UUID]) -> list[CompanyDocument]:
        if not document_ids:
            return []
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(CompanyDocumentModel).where(CompanyDocumentModel.id.in_(list(document_ids)))
            )
            models = list(result.scalars().all())
            ids = [model.id for model in models]
            grouped = await self._database_ids_many(session, ids)
            return [self._to_entity(model, grouped.get(model.id, frozenset())) for model in models]

    async def get_by_sha256(self, sha256: str) -> CompanyDocument | None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(CompanyDocumentModel).where(
                    CompanyDocumentModel.sha256 == sha256,
                    CompanyDocumentModel.deleted_at.is_(None),
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            database_ids = await self._database_ids(session, model.id)
            return self._to_entity(model, database_ids)

    async def list_documents(
        self,
        *,
        status: DocumentStatus | None = None,
        visibility: DocumentVisibility | None = None,
        module: ModuleCode | None = None,
        database_id: UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyDocument]:
        async with self._sessionmaker() as session:
            stmt = select(CompanyDocumentModel).where(CompanyDocumentModel.deleted_at.is_(None))
            if status is not None:
                stmt = stmt.where(CompanyDocumentModel.status == status.value)
            if visibility is not None:
                stmt = stmt.where(CompanyDocumentModel.visibility == visibility.value)
            if database_id is not None:
                in_scope = (
                    select(CompanyDocumentDatabaseModel.document_id)
                    .where(
                        CompanyDocumentDatabaseModel.document_id == CompanyDocumentModel.id,
                        CompanyDocumentDatabaseModel.erp_database_id == database_id,
                    )
                    .exists()
                )
                stmt = stmt.where(or_(CompanyDocumentModel.all_databases.is_(True), in_scope))
            if query and query.strip():
                stmt = stmt.where(CompanyDocumentModel.title.ilike(f"%{query.strip()}%"))
            stmt = stmt.order_by(CompanyDocumentModel.created_at.desc())

            if module is not None:
                result = await session.execute(stmt)
                filtered = [
                    model
                    for model in result.scalars().all()
                    if module.value in (model.modules or [])
                ]
                page = filtered[offset : offset + limit]
            else:
                result = await session.execute(stmt.limit(limit).offset(offset))
                page = list(result.scalars().all())

            grouped = await self._database_ids_many(session, [m.id for m in page])
            return [self._to_entity(model, grouped.get(model.id, frozenset())) for model in page]

    async def count_by_status(self) -> dict[DocumentStatus, int]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(
                    CompanyDocumentModel.status,
                    func.count(CompanyDocumentModel.id),
                )
                .where(CompanyDocumentModel.deleted_at.is_(None))
                .group_by(CompanyDocumentModel.status)
            )
            counts: dict[DocumentStatus, int] = dict.fromkeys(DocumentStatus, 0)
            for raw_status, total in result.all():
                counts[_to_status(str(raw_status))] = int(total)
            return counts

    async def total_chunks(self) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(select(func.count(CompanyDocumentChunkModel.id)))
            return int(result.scalar_one() or 0)

    async def total_bytes_stored(self) -> int:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(CompanyDocumentModel.size_bytes), 0)).where(
                    CompanyDocumentModel.deleted_at.is_(None)
                )
            )
            return int(result.scalar_one() or 0)

    async def list_ready_for_index(self, embedding_model: str) -> list[CompanyDocument]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(CompanyDocumentModel).where(
                    CompanyDocumentModel.status == DocumentStatus.READY.value,
                    CompanyDocumentModel.deleted_at.is_(None),
                    CompanyDocumentModel.embedding_model == embedding_model,
                )
            )
            models = list(result.scalars().all())
            grouped = await self._database_ids_many(session, [m.id for m in models])
            return [self._to_entity(model, grouped.get(model.id, frozenset())) for model in models]

    # ── Blobs ────────────────────────────────────────────────────────────
    async def save_blob(self, document_id: UUID, content: bytes) -> None:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyDocumentBlobModel, document_id)
            if model is None:
                session.add(CompanyDocumentBlobModel(document_id=document_id, content=content))
            else:
                model.content = content
            await session.commit()

    async def get_blob(self, document_id: UUID) -> bytes | None:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyDocumentBlobModel, document_id)
            return None if model is None else model.content

    # ── Fragmentos ───────────────────────────────────────────────────────
    async def replace_chunks(self, document_id: UUID, chunks: Sequence[PendingChunk]) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(CompanyDocumentChunkModel).where(
                    CompanyDocumentChunkModel.document_id == document_id
                )
            )
            session.add_all(
                [
                    CompanyDocumentChunkModel(
                        document_id=document_id,
                        ordinal=chunk.ordinal,
                        page_from=chunk.page_from,
                        page_to=chunk.page_to,
                        heading=chunk.heading,
                        text=chunk.text,
                        embedding=chunk.embedding,
                    )
                    for chunk in chunks
                ]
            )
            await session.commit()

    async def delete_chunks(self, document_id: UUID) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(CompanyDocumentChunkModel).where(
                    CompanyDocumentChunkModel.document_id == document_id
                )
            )
            await session.commit()

    async def list_chunks(self, document_id: UUID) -> list[DocumentChunk]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(CompanyDocumentChunkModel)
                .where(CompanyDocumentChunkModel.document_id == document_id)
                .order_by(CompanyDocumentChunkModel.ordinal.asc())
            )
            return [
                DocumentChunk(
                    id=model.id,
                    document_id=model.document_id,
                    ordinal=model.ordinal,
                    page_from=model.page_from,
                    page_to=model.page_to,
                    heading=model.heading,
                    text=model.text,
                    embedding=model.embedding,
                    created_at=model.created_at,
                )
                for model in result.scalars().all()
            ]

    # ── Worker ───────────────────────────────────────────────────────────
    async def claim_next_pending(self) -> CompanyDocument | None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(CompanyDocumentModel)
                .where(
                    CompanyDocumentModel.status == DocumentStatus.PENDING.value,
                    CompanyDocumentModel.deleted_at.is_(None),
                )
                .order_by(CompanyDocumentModel.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            model.status = DocumentStatus.PROCESSING.value
            model.updated_at = _now()
            database_ids = await self._database_ids(session, model.id)
            entity = self._to_entity(model, database_ids)
            await session.commit()
            return entity

    async def requeue_processing(self) -> int:
        async with self._sessionmaker() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(CompanyDocumentModel)
                    .where(CompanyDocumentModel.status == DocumentStatus.PROCESSING.value)
                    .values(status=DocumentStatus.PENDING.value, updated_at=_now())
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def enqueue_stale_embedding_documents(self, current_model: str) -> int:
        async with self._sessionmaker() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(CompanyDocumentModel)
                    .where(
                        CompanyDocumentModel.status == DocumentStatus.READY.value,
                        CompanyDocumentModel.deleted_at.is_(None),
                        CompanyDocumentModel.embedding_model.is_not(None),
                        CompanyDocumentModel.embedding_model != current_model,
                    )
                    .values(status=DocumentStatus.PENDING.value, updated_at=_now())
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def complete_processing(
        self, document_id: UUID, expected_version: int, outcome: ProcessingOutcome
    ) -> bool:
        async with self._sessionmaker() as session:
            model = await self._claimed_model(session, document_id, expected_version)
            if model is None:
                return False
            # Fragmentos y estado en la MISMA transacción: un fallo a mitad
            # no deja un documento `ready` sin fragmentos ni fragmentos
            # huérfanos de un documento `failed`.
            await session.execute(
                delete(CompanyDocumentChunkModel).where(
                    CompanyDocumentChunkModel.document_id == document_id
                )
            )
            is_ready = outcome.status == DocumentStatus.READY
            if is_ready:
                session.add_all(
                    [
                        CompanyDocumentChunkModel(
                            document_id=document_id,
                            ordinal=chunk.ordinal,
                            page_from=chunk.page_from,
                            page_to=chunk.page_to,
                            heading=chunk.heading,
                            text=chunk.text,
                            embedding=chunk.embedding,
                        )
                        for chunk in outcome.chunks
                    ]
                )
            now = _now()
            model.status = outcome.status.value
            model.status_code = outcome.status_code.value if outcome.status_code else None
            model.page_count = outcome.page_count
            model.char_count = outcome.char_count
            model.chunk_count = len(outcome.chunks) if is_ready else 0
            model.embedding_model = outcome.embedding_model if is_ready else None
            model.processed_at = now
            model.updated_at = now
            await session.commit()
            return True

    async def release_claim(self, document_id: UUID, expected_version: int) -> bool:
        async with self._sessionmaker() as session:
            model = await self._claimed_model(session, document_id, expected_version)
            if model is None:
                return False
            model.status = DocumentStatus.PENDING.value
            model.updated_at = _now()
            await session.commit()
            return True

    async def _claimed_model(
        self, session: AsyncSession, document_id: UUID, expected_version: int
    ) -> CompanyDocumentModel | None:
        """El documento solo si sigue tomado por el worker en esa versión."""
        result = await session.execute(
            select(CompanyDocumentModel)
            .where(
                CompanyDocumentModel.id == document_id,
                CompanyDocumentModel.deleted_at.is_(None),
                CompanyDocumentModel.version == expected_version,
                CompanyDocumentModel.status == DocumentStatus.PROCESSING.value,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    # ── Baja ─────────────────────────────────────────────────────────────
    async def soft_delete(self, document_id: UUID) -> bool:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyDocumentModel, document_id)
            if model is None or model.deleted_at is not None:
                return False
            model.deleted_at = _now()
            model.updated_at = _now()
            await session.execute(
                delete(CompanyDocumentBlobModel).where(
                    CompanyDocumentBlobModel.document_id == document_id
                )
            )
            await session.execute(
                delete(CompanyDocumentChunkModel).where(
                    CompanyDocumentChunkModel.document_id == document_id
                )
            )
            await session.execute(
                delete(CompanyDocumentDatabaseModel).where(
                    CompanyDocumentDatabaseModel.document_id == document_id
                )
            )
            await session.commit()
            return True

    # ── Internos ─────────────────────────────────────────────────────────
    async def _replace_databases(self, session: AsyncSession, document: CompanyDocument) -> None:
        await session.execute(
            delete(CompanyDocumentDatabaseModel).where(
                CompanyDocumentDatabaseModel.document_id == document.id
            )
        )
        if not document.all_databases and document.database_ids:
            session.add_all(
                [
                    CompanyDocumentDatabaseModel(
                        document_id=document.id, erp_database_id=database_id
                    )
                    for database_id in document.database_ids
                ]
            )

    async def _database_ids(self, session: AsyncSession, document_id: UUID) -> frozenset[UUID]:
        result = await session.execute(
            select(CompanyDocumentDatabaseModel.erp_database_id).where(
                CompanyDocumentDatabaseModel.document_id == document_id
            )
        )
        return frozenset(result.scalars().all())

    async def _database_ids_many(
        self, session: AsyncSession, document_ids: Sequence[UUID]
    ) -> dict[UUID, frozenset[UUID]]:
        grouped: dict[UUID, set[UUID]] = {}
        if not document_ids:
            return {}
        result = await session.execute(
            select(
                CompanyDocumentDatabaseModel.document_id,
                CompanyDocumentDatabaseModel.erp_database_id,
            ).where(CompanyDocumentDatabaseModel.document_id.in_(list(document_ids)))
        )
        for document_id, erp_database_id in result.all():
            grouped.setdefault(document_id, set()).add(erp_database_id)
        return {document_id: frozenset(ids) for document_id, ids in grouped.items()}

    @staticmethod
    def _to_entity(model: CompanyDocumentModel, database_ids: frozenset[UUID]) -> CompanyDocument:
        return CompanyDocument(
            id=model.id,
            title=model.title,
            original_filename=model.original_filename,
            media_type=model.media_type,
            size_bytes=model.size_bytes,
            sha256=model.sha256,
            version=model.version,
            status=_to_status(model.status),
            status_code=_to_status_code(model.status_code),
            page_count=model.page_count,
            chunk_count=model.chunk_count,
            char_count=model.char_count,
            embedding_model=model.embedding_model,
            visibility=_to_visibility(model.visibility),
            modules=_to_modules(model.modules or []),
            all_databases=model.all_databases,
            database_ids=sorted(database_ids),
            uploaded_by_login=model.uploaded_by_login,
            uploaded_by_database_id=model.uploaded_by_database_id,
            uploaded_by_user_id=model.uploaded_by_user_id,
            processed_at=model.processed_at,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(document: CompanyDocument) -> CompanyDocumentModel:
        return CompanyDocumentModel(
            id=document.id,
            title=document.title,
            original_filename=document.original_filename,
            media_type=document.media_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            version=document.version,
            status=document.status.value,
            status_code=document.status_code.value if document.status_code else None,
            page_count=document.page_count,
            chunk_count=document.chunk_count,
            char_count=document.char_count,
            embedding_model=document.embedding_model,
            visibility=document.visibility.value,
            modules=[module.value for module in document.modules],
            all_databases=document.all_databases,
            uploaded_by_login=document.uploaded_by_login,
            uploaded_by_database_id=_required_database_id(document),
            uploaded_by_user_id=document.uploaded_by_user_id,
            processed_at=document.processed_at,
            deleted_at=document.deleted_at,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @staticmethod
    def _apply(model: CompanyDocumentModel, document: CompanyDocument) -> None:
        model.title = document.title
        model.original_filename = document.original_filename
        model.media_type = document.media_type
        model.size_bytes = document.size_bytes
        model.sha256 = document.sha256
        model.version = document.version
        model.status = document.status.value
        model.status_code = document.status_code.value if document.status_code else None
        model.page_count = document.page_count
        model.chunk_count = document.chunk_count
        model.char_count = document.char_count
        model.embedding_model = document.embedding_model
        model.visibility = document.visibility.value
        model.modules = [module.value for module in document.modules]
        model.all_databases = document.all_databases
        model.uploaded_by_login = document.uploaded_by_login
        model.uploaded_by_database_id = _required_database_id(document)
        model.uploaded_by_user_id = document.uploaded_by_user_id
        model.processed_at = document.processed_at
        model.deleted_at = document.deleted_at
        model.updated_at = _now()
