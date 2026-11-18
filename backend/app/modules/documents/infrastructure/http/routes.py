"""Conjuntos de resultados: vista previa para el chat y exportación completa."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.infrastructure.database import get_agent_sessionmaker
from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.documents.application.file_use_cases import DownloadFileUseCase
from app.modules.documents.application.use_cases import (
    PREVIEW_MAX_ROWS,
    ExportResultSetUseCase,
    GetResultSetUseCase,
    Owner,
)
from app.modules.documents.domain.files import FileFormat
from app.modules.documents.infrastructure.branding import read_branding
from app.modules.documents.infrastructure.exporters import FileRenderer
from app.modules.documents.infrastructure.repository import (
    SqlAlchemyResultSetRepository,
    SqlAlchemyStoredFileRepository,
)

router = APIRouter(prefix="/result-sets", tags=["documents"])


class ResultColumnResponse(BaseModel):
    key: str
    label: str
    kind: str


class ResultSetPreviewResponse(BaseModel):
    id: UUID
    title: str
    columns: list[ResultColumnResponse]
    rows: list[list[Any]]
    total_rows: int
    total_is_lower_bound: bool
    created_at: datetime


def _repository() -> SqlAlchemyResultSetRepository:
    return SqlAlchemyResultSetRepository(get_agent_sessionmaker())


RepositoryDep = Annotated[SqlAlchemyResultSetRepository, Depends(_repository)]


def _owner(user: CurrentUserDep) -> Owner:
    assert user.erp_database_id is not None  # noqa: S101 — el token no decodifica sin base
    return Owner(user_id=user.id, erp_database_id=user.erp_database_id)


@router.get("/{result_set_id}", response_model=ResultSetPreviewResponse)
async def get_preview(
    result_set_id: UUID,
    user: CurrentUserDep,
    repository: RepositoryDep,
    limit: Annotated[int, Query(ge=1, le=PREVIEW_MAX_ROWS)] = PREVIEW_MAX_ROWS,
) -> ResultSetPreviewResponse:
    table = await GetResultSetUseCase(repository).execute(result_set_id, _owner(user))
    return ResultSetPreviewResponse(
        id=table.id,
        title=table.title,
        columns=[
            ResultColumnResponse(key=c.key, label=c.label, kind=c.kind) for c in table.columns
        ],
        rows=table.rows[:limit],
        total_rows=table.total_rows,
        total_is_lower_bound=table.total_is_lower_bound,
        created_at=table.created_at,
    )


@router.get("/{result_set_id}/export")
async def export(
    result_set_id: UUID,
    user: CurrentUserDep,
    repository: RepositoryDep,
    format: Annotated[FileFormat, Query()] = FileFormat.XLSX,  # noqa: A002 — nombre del parámetro en la URL
) -> Response:
    generated = await ExportResultSetUseCase(repository, FileRenderer()).execute(
        result_set_id, _owner(user), format, await read_branding(user.erp_database_id)
    )
    return Response(
        content=generated.content,
        media_type=generated.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(generated.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


files_router = APIRouter(prefix="/files", tags=["documents"])


def _files() -> SqlAlchemyStoredFileRepository:
    return SqlAlchemyStoredFileRepository(get_agent_sessionmaker())


FilesDep = Annotated[SqlAlchemyStoredFileRepository, Depends(_files)]


@files_router.get("/{file_id}")
async def download_file(file_id: UUID, user: CurrentUserDep, files: FilesDep) -> Response:
    stored = await DownloadFileUseCase(files).execute(file_id, _owner(user))
    return Response(
        content=stored.content,
        media_type=stored.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(stored.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
