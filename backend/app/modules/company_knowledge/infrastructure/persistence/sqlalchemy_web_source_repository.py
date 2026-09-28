"""Persistencia de fuentes web y sus páginas (Fase 5)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.web_source import WebPage, WebSource
from app.modules.company_knowledge.domain.interfaces import WebSourceRepository
from app.modules.company_knowledge.domain.value_objects import (
    DocumentVisibility,
    RefreshFrequency,
    WebPageStatus,
    WebSourceMode,
    WebSourceStatus,
    WebSourceStatusCode,
)
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyWebPageModel,
    CompanyWebSourceDatabaseModel,
    CompanyWebSourceModel,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _modules(values: Sequence[str]) -> list[ModuleCode]:
    modules: list[ModuleCode] = []
    for value in values:
        try:
            modules.append(ModuleCode(value))
        except ValueError:
            continue
    return modules


def _status_code(value: str | None) -> WebSourceStatusCode | None:
    if value is None:
        return None
    try:
        return WebSourceStatusCode(value)
    except ValueError:
        return WebSourceStatusCode.INTERNAL_ERROR


class SqlAlchemyWebSourceRepository(WebSourceRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    # ── Fuentes ──────────────────────────────────────────────────────────
    async def save(self, source: WebSource) -> WebSource:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyWebSourceModel, source.id)
            if model is None:
                model = CompanyWebSourceModel(id=source.id, created_at=source.created_at)
                self._apply(model, source)
                session.add(model)
                # Sin `relationship`: el alcance por base se inserta después
                # del padre o Postgres rechaza la FK.
                await session.flush()
            else:
                self._apply(model, source)
            await session.execute(
                delete(CompanyWebSourceDatabaseModel).where(
                    CompanyWebSourceDatabaseModel.source_id == source.id
                )
            )
            if not source.all_databases:
                session.add_all(
                    [
                        CompanyWebSourceDatabaseModel(source_id=source.id, erp_database_id=db)
                        for db in source.database_ids
                    ]
                )
            await session.commit()
        return source

    async def get_by_id(self, source_id: UUID) -> WebSource | None:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyWebSourceModel, source_id)
            if model is None:
                return None
            return self._to_entity(model, await self._database_ids(session, source_id))

    async def list_sources(self) -> list[WebSource]:
        async with self._sessionmaker() as session:
            models = (
                await session.scalars(
                    select(CompanyWebSourceModel)
                    .where(CompanyWebSourceModel.deleted_at.is_(None))
                    .order_by(CompanyWebSourceModel.created_at.desc())
                )
            ).all()
            return [self._to_entity(m, await self._database_ids(session, m.id)) for m in models]

    async def count_active(self) -> int:
        async with self._sessionmaker() as session:
            total = await session.scalar(
                select(func.count())
                .select_from(CompanyWebSourceModel)
                .where(CompanyWebSourceModel.deleted_at.is_(None))
            )
            return int(total or 0)

    async def claim_next_due(self) -> WebSource | None:
        async with self._sessionmaker() as session:
            model = await session.scalar(
                select(CompanyWebSourceModel)
                .where(
                    CompanyWebSourceModel.status == WebSourceStatus.PENDING.value,
                    CompanyWebSourceModel.deleted_at.is_(None),
                )
                .order_by(CompanyWebSourceModel.updated_at)
                .limit(1)
            )
            if model is None:
                return None
            # Condicional: si otro proceso la tomó entre el SELECT y acá, no
            # se procesa dos veces.
            claimed = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(CompanyWebSourceModel)
                    .where(
                        CompanyWebSourceModel.id == model.id,
                        CompanyWebSourceModel.status == WebSourceStatus.PENDING.value,
                    )
                    .values(
                        status=WebSourceStatus.CRAWLING.value,
                        last_crawl_started_at=_now(),
                        updated_at=_now(),
                    )
                ),
            )
            await session.commit()
            if claimed.rowcount == 0:
                return None
        return await self.get_by_id(model.id)

    async def requeue_crawling(self) -> int:
        async with self._sessionmaker() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(CompanyWebSourceModel)
                    .where(CompanyWebSourceModel.status == WebSourceStatus.CRAWLING.value)
                    .values(status=WebSourceStatus.PENDING.value)
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def enqueue_due_refreshes(self) -> int:
        async with self._sessionmaker() as session:
            result = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(CompanyWebSourceModel)
                    .where(
                        CompanyWebSourceModel.deleted_at.is_(None),
                        CompanyWebSourceModel.refresh != RefreshFrequency.MANUAL.value,
                        CompanyWebSourceModel.status.in_(
                            [WebSourceStatus.READY.value, WebSourceStatus.FAILED.value]
                        ),
                        CompanyWebSourceModel.next_refresh_at.is_not(None),
                        CompanyWebSourceModel.next_refresh_at <= _now(),
                    )
                    .values(status=WebSourceStatus.PENDING.value, updated_at=_now())
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def soft_delete(self, source_id: UUID) -> bool:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyWebSourceModel, source_id)
            if model is None or model.deleted_at is not None:
                return False
            model.deleted_at = _now()
            model.updated_at = _now()
            await session.commit()
            return True

    # ── Páginas ──────────────────────────────────────────────────────────
    async def list_pages(self, source_id: UUID) -> list[WebPage]:
        async with self._sessionmaker() as session:
            models = (
                await session.scalars(
                    select(CompanyWebPageModel)
                    .where(CompanyWebPageModel.source_id == source_id)
                    .order_by(CompanyWebPageModel.url)
                )
            ).all()
            return [self._page_entity(m) for m in models]

    async def save_page(self, page: WebPage) -> None:
        async with self._sessionmaker() as session:
            model = await session.get(CompanyWebPageModel, page.document_id)
            if model is None:
                model = CompanyWebPageModel(document_id=page.document_id)
                session.add(model)
            model.source_id = page.source_id
            model.url = page.url
            model.title = page.title[:200]
            model.status = page.status.value
            model.status_detail = (page.status_detail or "")[:300] or None
            model.etag = page.etag
            model.last_modified = page.last_modified
            model.content_hash = page.content_hash
            model.missing_count = page.missing_count
            model.last_fetched_at = page.last_fetched_at
            model.last_changed_at = page.last_changed_at
            await session.commit()

    async def delete_page(self, document_id: UUID) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(CompanyWebPageModel).where(CompanyWebPageModel.document_id == document_id)
            )
            await session.commit()

    # ── Internos ─────────────────────────────────────────────────────────
    async def _database_ids(self, session: AsyncSession, source_id: UUID) -> list[UUID]:
        rows = await session.scalars(
            select(CompanyWebSourceDatabaseModel.erp_database_id).where(
                CompanyWebSourceDatabaseModel.source_id == source_id
            )
        )
        return sorted(rows.all())

    @staticmethod
    def _apply(model: CompanyWebSourceModel, source: WebSource) -> None:
        if source.created_by_database_id is None:
            raise ValueError("La fuente web necesita la base de quien la creó.")
        model.url = source.url
        model.mode = source.mode.value
        model.title = source.title[:200]
        model.refresh = source.refresh.value
        model.max_pages = source.max_pages
        model.excluded_sections = list(source.excluded_sections)
        model.visibility = source.visibility.value
        model.modules = [module.value for module in source.modules]
        model.all_databases = source.all_databases
        model.status = source.status.value
        model.status_code = source.status_code.value if source.status_code else None
        model.status_message = (source.status_message or "")[:500] or None
        model.page_count = source.page_count
        model.skipped_count = source.skipped_count
        model.last_crawl_started_at = source.last_crawl_started_at
        model.last_crawl_finished_at = source.last_crawl_finished_at
        model.next_refresh_at = source.next_refresh_at
        model.created_by_login = source.created_by_login
        model.created_by_database_id = source.created_by_database_id
        model.created_by_user_id = source.created_by_user_id
        model.deleted_at = source.deleted_at
        model.updated_at = _now()

    @staticmethod
    def _to_entity(model: CompanyWebSourceModel, database_ids: list[UUID]) -> WebSource:
        return WebSource(
            id=model.id,
            url=model.url,
            mode=WebSourceMode(model.mode),
            title=model.title,
            refresh=RefreshFrequency(model.refresh),
            max_pages=model.max_pages,
            excluded_sections=list(model.excluded_sections or []),
            visibility=DocumentVisibility(model.visibility),
            modules=_modules(model.modules or []),
            all_databases=model.all_databases,
            database_ids=database_ids,
            status=WebSourceStatus(model.status),
            status_code=_status_code(model.status_code),
            status_message=model.status_message,
            page_count=model.page_count,
            skipped_count=model.skipped_count,
            last_crawl_started_at=model.last_crawl_started_at,
            last_crawl_finished_at=model.last_crawl_finished_at,
            next_refresh_at=model.next_refresh_at,
            created_by_login=model.created_by_login,
            created_by_database_id=model.created_by_database_id,
            created_by_user_id=model.created_by_user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def _page_entity(model: CompanyWebPageModel) -> WebPage:
        try:
            status = WebPageStatus(model.status)
        except ValueError:
            status = WebPageStatus.FAILED
        return WebPage(
            document_id=model.document_id,
            source_id=model.source_id,
            url=model.url,
            title=model.title,
            status=status,
            status_detail=model.status_detail,
            etag=model.etag,
            last_modified=model.last_modified,
            content_hash=model.content_hash,
            missing_count=model.missing_count,
            last_fetched_at=model.last_fetched_at,
            last_changed_at=model.last_changed_at,
        )
