"""Vista previa y exportación de un conjunto de resultados, solo para su dueño."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.modules.documents.domain.document import Branding, Document
from app.modules.documents.domain.files import (
    TABLE_FORMATS,
    DocumentRenderer,
    FileFormat,
    safe_filename,
)
from app.modules.documents.domain.interfaces import ResultSetRepository
from app.modules.documents.domain.result_set import ResultSet
from app.shared.exceptions import NotFoundError, ValidationError

audit_log = logging.getLogger("savi.audit")

# Filas de la vista previa en el chat. Lo completo va por Exportar.
PREVIEW_MAX_ROWS = 30


@dataclass(frozen=True)
class Owner:
    user_id: int
    erp_database_id: UUID


@dataclass(frozen=True)
class GeneratedFile:
    content: bytes
    filename: str
    media_type: str


def _not_found() -> NotFoundError:
    # Mismo error para "no existe" y "es de otro": no se confirma qué ids existen.
    return NotFoundError("Ese conjunto de datos no existe o ya venció.")


class GetResultSetUseCase:
    def __init__(self, repository: ResultSetRepository) -> None:
        self._repository = repository

    async def execute(self, result_set_id: UUID, owner: Owner) -> ResultSet:
        found = await self._repository.get_owned(
            result_set_id, user_id=owner.user_id, owner_erp_database_id=owner.erp_database_id
        )
        if found is None:
            raise _not_found()
        return found


class ExportResultSetUseCase:
    def __init__(self, repository: ResultSetRepository, renderer: DocumentRenderer) -> None:
        self._repository = repository
        self._renderer = renderer

    async def execute(
        self,
        result_set_id: UUID,
        owner: Owner,
        file_format: FileFormat,
        branding: Branding | None = None,
    ) -> GeneratedFile:
        if file_format not in TABLE_FORMATS:
            raise ValidationError("Una tabla se exporta en Excel, PDF o CSV.")
        table = await GetResultSetUseCase(self._repository).execute(result_set_id, owner)
        document = Document.for_table(table, generated_at=datetime.now(UTC), branding=branding)
        # Generar 10.000 filas en PDF bloquearía el event loop.
        content = await asyncio.to_thread(self._renderer.render, document, file_format)
        if table.has_personal_data:
            audit_log.info(
                "personal_data_export user_id=%s erp_database_id=%s result_set=%s "
                "format=%s rows=%s",
                owner.user_id,
                owner.erp_database_id,
                table.id,
                file_format.value,
                table.total_rows,
            )
        return GeneratedFile(
            content=content,
            filename=safe_filename(table.title, file_format.value),
            media_type=file_format.media_type,
        )
