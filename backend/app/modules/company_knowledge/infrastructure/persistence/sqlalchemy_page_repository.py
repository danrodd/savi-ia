"""Páginas leídas, registro de gasto y configuración del módulo (Fase 4)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.company_knowledge.domain.entities.page_reading import (
    AiReadRecord,
    KnowledgeSettings,
    ReadPage,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentPageRepository,
    KnowledgeSettingsRepository,
)
from app.modules.company_knowledge.domain.value_objects import (
    AiReadErrorCode,
    PageRoute,
)
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentAiReadModel,
    CompanyDocumentPageModel,
    CompanyKnowledgeSettingsModel,
)

_SETTINGS_ID = 1


def _to_error(value: str | None) -> AiReadErrorCode | None:
    if value is None:
        return None
    try:
        return AiReadErrorCode(value)
    except ValueError:
        return AiReadErrorCode.PROVIDER_ERROR


class SqlAlchemyDocumentPageRepository(DocumentPageRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def list_pages(self, document_id: UUID, version: int) -> list[ReadPage]:
        async with self._sessionmaker() as session:
            rows = (
                await session.scalars(
                    select(CompanyDocumentPageModel)
                    .where(
                        CompanyDocumentPageModel.document_id == document_id,
                        CompanyDocumentPageModel.version == version,
                    )
                    .order_by(CompanyDocumentPageModel.page_number)
                )
            ).all()
        return [
            ReadPage(
                page_number=row.page_number,
                method=PageRoute(row.method),
                text=row.text,
                pypdf_chars=row.pypdf_chars,
                image_count=row.image_count,
                max_image_pixels=row.max_image_pixels,
                page_type=row.page_type,
                legible=row.legible,
                ai_error=_to_error(row.ai_error),
                prompt_version=row.prompt_version,
            )
            for row in rows
        ]

    async def save_pages(self, document_id: UUID, version: int, pages: Sequence[ReadPage]) -> None:
        if not pages:
            return
        async with self._sessionmaker() as session:
            # Reemplazo por clave: portable entre Postgres y SQLite sin
            # depender de `ON CONFLICT` de cada motor.
            await session.execute(
                delete(CompanyDocumentPageModel).where(
                    CompanyDocumentPageModel.document_id == document_id,
                    CompanyDocumentPageModel.version == version,
                    CompanyDocumentPageModel.page_number.in_([p.page_number for p in pages]),
                )
            )
            session.add_all(
                [
                    CompanyDocumentPageModel(
                        document_id=document_id,
                        version=version,
                        page_number=page.page_number,
                        method=page.method.value,
                        page_type=page.page_type,
                        legible=page.legible,
                        text=page.text,
                        pypdf_chars=page.pypdf_chars,
                        image_count=page.image_count,
                        max_image_pixels=page.max_image_pixels,
                        ai_error=page.ai_error.value if page.ai_error else None,
                        prompt_version=page.prompt_version,
                    )
                    for page in pages
                ]
            )
            await session.commit()

    async def delete_ai_pages(self, document_id: UUID, version: int) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(CompanyDocumentPageModel).where(
                    CompanyDocumentPageModel.document_id == document_id,
                    CompanyDocumentPageModel.version == version,
                    CompanyDocumentPageModel.method == PageRoute.AI.value,
                )
            )
            await session.commit()

    async def delete_other_versions(self, document_id: UUID, keep_version: int) -> None:
        async with self._sessionmaker() as session:
            await session.execute(
                delete(CompanyDocumentPageModel).where(
                    CompanyDocumentPageModel.document_id == document_id,
                    CompanyDocumentPageModel.version != keep_version,
                )
            )
            await session.commit()

    async def record_ai_read(self, record: AiReadRecord) -> None:
        async with self._sessionmaker() as session:
            session.add(
                CompanyDocumentAiReadModel(
                    document_id=record.document_id,
                    version=record.version,
                    page_from=record.page_from,
                    page_to=record.page_to,
                    provider=record.provider,
                    model=record.model,
                    input_tokens=record.usage.input_tokens,
                    output_tokens=record.usage.output_tokens,
                    cost_usd=(
                        None
                        if record.usage.cost_usd is None
                        else Decimal(str(round(record.usage.cost_usd, 6)))
                    ),
                    outcome=record.outcome.value,
                    uploaded_by_login=record.uploaded_by_login,
                    uploaded_by_database_id=record.uploaded_by_database_id,
                )
            )
            await session.commit()

    async def ai_cost(self, document_id: UUID, version: int) -> float | None:
        async with self._sessionmaker() as session:
            total = await session.scalar(
                select(func.sum(CompanyDocumentAiReadModel.cost_usd)).where(
                    CompanyDocumentAiReadModel.document_id == document_id,
                    CompanyDocumentAiReadModel.version == version,
                )
            )
        return None if total is None else float(total)

    async def average_cost_per_page(self, provider: str, model: str) -> float | None:
        pages = CompanyDocumentAiReadModel.page_to - CompanyDocumentAiReadModel.page_from + 1
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(
                        func.sum(CompanyDocumentAiReadModel.cost_usd),
                        func.sum(pages),
                    ).where(
                        and_(
                            CompanyDocumentAiReadModel.provider == provider,
                            CompanyDocumentAiReadModel.model == model,
                            CompanyDocumentAiReadModel.cost_usd.is_not(None),
                        )
                    )
                )
            ).one()
        cost, page_total = row
        if cost is None or not page_total:
            return None
        return float(cost) / int(page_total)


class SqlAlchemyKnowledgeSettingsRepository(KnowledgeSettingsRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self) -> KnowledgeSettings:
        async with self._sessionmaker() as session:
            row = await session.get(CompanyKnowledgeSettingsModel, _SETTINGS_ID)
        if row is None:
            return KnowledgeSettings()
        return KnowledgeSettings(
            ai_reading_enabled=row.ai_reading_enabled,
            updated_by_login=row.updated_by_login,
            updated_at=row.updated_at,
        )

    async def save(self, settings: KnowledgeSettings) -> KnowledgeSettings:
        async with self._sessionmaker() as session:
            row = await session.get(CompanyKnowledgeSettingsModel, _SETTINGS_ID)
            if row is None:
                row = CompanyKnowledgeSettingsModel(id=_SETTINGS_ID)
                session.add(row)
            row.ai_reading_enabled = settings.ai_reading_enabled
            row.updated_by_login = settings.updated_by_login
            row.updated_at = datetime.now(UTC)
            await session.commit()
        return await self.get()
