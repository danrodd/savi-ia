"""Archivos que SAVI entrega en el chat: exportar un conjunto o armar un documento."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from app.modules.documents.application.document_spec import (
    MAX_TABLES,
    BulletsBlock,
    DocumentSpec,
    HeadingBlock,
    KeyValuesBlock,
    ParagraphBlock,
)
from app.modules.documents.application.use_cases import Owner
from app.modules.documents.domain.document import Block, Branding, Document
from app.modules.documents.domain.files import (
    TABLE_FORMATS,
    DocumentRenderer,
    FileFormat,
    safe_filename,
)
from app.modules.documents.domain.interfaces import ResultSetRepository, StoredFileRepository
from app.modules.documents.domain.result_set import ResultSet
from app.modules.documents.domain.stored_file import StoredFile
from app.shared.exceptions import NotFoundError, ValidationError

audit_log = logging.getLogger("savi.audit")


class FileRequestError(ValidationError):
    """Pedido de archivo que no se puede cumplir; el texto es para el modelo."""


class ExportToFileUseCase:
    """`entregar_archivo` tipo `exportar`: un conjunto de la conversación a un archivo."""

    def __init__(
        self,
        result_sets: ResultSetRepository,
        files: StoredFileRepository,
        renderer: DocumentRenderer,
    ) -> None:
        self._result_sets = result_sets
        self._files = files
        self._renderer = renderer

    async def execute(
        self,
        conversation_id: UUID,
        file_format: FileFormat,
        result_set_id: UUID | None,
        branding: Branding,
    ) -> StoredFile:
        if file_format not in TABLE_FORMATS:
            raise FileRequestError("Una tabla se exporta en xlsx, pdf o csv.")
        table = (
            await self._result_sets.get_in_conversation(result_set_id, conversation_id)
            if result_set_id is not None
            else await self._result_sets.latest_in_conversation(conversation_id)
        )
        if table is None:
            raise FileRequestError(
                "No hay un conjunto de datos de esta conversación para exportar. Primero "
                "consulta los datos con consultar_datos o consultar_libre."
            )
        document = Document.for_table(table, generated_at=datetime.now(UTC), branding=branding)
        content = await asyncio.to_thread(self._renderer.render, document, file_format)
        stored = StoredFile(
            conversation_id=conversation_id,
            filename=safe_filename(table.title, file_format.value),
            media_type=file_format.media_type,
            content=content,
            has_personal_data=table.has_personal_data,
        )
        await self._files.add(stored)
        return stored


class BuildDocumentUseCase:
    """`entregar_archivo` tipo `documento`: la especificación validada a PDF o Word."""

    def __init__(
        self,
        result_sets: ResultSetRepository,
        files: StoredFileRepository,
        renderer: DocumentRenderer,
    ) -> None:
        self._result_sets = result_sets
        self._files = files
        self._renderer = renderer

    async def execute(
        self, conversation_id: UUID, spec: DocumentSpec, branding: Branding
    ) -> StoredFile:
        if len(spec.table_ids()) > MAX_TABLES:
            raise FileRequestError(f"Un documento puede tener hasta {MAX_TABLES} tablas.")
        blocks: list[Block] = []
        personal = False
        for item in spec.bloques:
            if isinstance(item, HeadingBlock):
                blocks.append(Block(kind="heading", text=item.texto))
            elif isinstance(item, ParagraphBlock):
                blocks.append(Block(kind="paragraph", text=item.texto))
            elif isinstance(item, BulletsBlock):
                blocks.append(Block(kind="bullets", items=tuple(item.items)))
            elif isinstance(item, KeyValuesBlock):
                blocks.append(Block(kind="key_values", pairs=tuple(item.items)))
            else:
                # Solo conjuntos de ESTA conversación: el modelo no puede traer
                # datos de otra conversación ni de otro usuario.
                table = await self._result_sets.get_in_conversation(item.conjunto, conversation_id)
                if table is None:
                    raise FileRequestError(
                        f"El conjunto {item.conjunto} no existe en esta conversación o venció. "
                        "Usa el identificador que te dio la consulta."
                    )
                personal = personal or table.has_personal_data
                columns = _resolve_columns(table, item.columnas)
                blocks.append(Block(kind="table", table=table, columns=columns))
        document = Document(
            title=spec.titulo,
            generated_at=datetime.now(UTC),
            company=branding.name,
            blocks=tuple(blocks),
            logo_png=branding.logo_png,
        )
        file_format = FileFormat(spec.formato)
        content = await asyncio.to_thread(self._renderer.render, document, file_format)
        stored = StoredFile(
            conversation_id=conversation_id,
            filename=safe_filename(spec.titulo, file_format.value),
            media_type=file_format.media_type,
            content=content,
            has_personal_data=personal,
        )
        await self._files.add(stored)
        return stored


def _resolve_columns(table: ResultSet, requested: list[str]) -> tuple[str, ...]:
    """Las columnas pedidas, por su clave o por su etiqueta, sin importar mayúsculas.

    Una columna que no existe se le explica al modelo con la lista de las que sí
    hay: antes salía un PDF con la tabla vacía, o una falla interna.
    """
    if not requested:
        return ()
    by_name = {c.key.casefold(): c.key for c in table.columns}
    by_name.update({c.label.casefold(): c.key for c in table.columns})
    unknown = [name for name in requested if name.casefold() not in by_name]
    if unknown:
        valid = ", ".join(c.key for c in table.columns)
        raise FileRequestError(
            f"Las columnas {', '.join(unknown)} no están en el conjunto. Usa algunas de: {valid}."
        )
    return tuple(dict.fromkeys(by_name[name.casefold()] for name in requested))


class DownloadFileUseCase:
    def __init__(self, files: StoredFileRepository) -> None:
        self._files = files

    async def execute(self, file_id: UUID, owner: Owner) -> StoredFile:
        stored = await self._files.get_owned(
            file_id, user_id=owner.user_id, owner_erp_database_id=owner.erp_database_id
        )
        if stored is None:
            raise NotFoundError("Ese archivo no existe o ya venció.")
        if stored.has_personal_data:
            audit_log.info(
                "personal_data_download user_id=%s erp_database_id=%s file=%s",
                owner.user_id,
                owner.erp_database_id,
                stored.id,
            )
        return stored
