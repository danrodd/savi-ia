"""Responses del módulo.

**Ninguna incluye la contraseña**, ni en claro ni cifrada. Se construyen
desde `ErpDatabaseDTO`, que directamente no tiene el campo: la regla es
estructural y no depende de que alguien se acuerde de omitirlo.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.erp_databases.application.dtos import (
    AvailableDatabaseDTO,
    ErpDatabaseDTO,
    ExportPayloadDTO,
    ImportResultDTO,
)
from app.modules.erp_databases.domain.interfaces import ConnectionTestResult


class ErpDatabaseResponse(BaseModel):
    id: UUID
    code: str
    name: str
    host: str
    port: int
    database: str
    username: str
    statement_timeout_ms: int
    is_default: bool
    is_active: bool
    credentials_unreadable: bool
    is_usable: bool
    last_connection_ok_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, dto: ErpDatabaseDTO) -> ErpDatabaseResponse:
        return cls(
            id=dto.id,
            code=dto.code,
            name=dto.name,
            host=dto.host,
            port=dto.port,
            database=dto.database,
            username=dto.username,
            statement_timeout_ms=dto.statement_timeout_ms,
            is_default=dto.is_default,
            is_active=dto.is_active,
            credentials_unreadable=dto.credentials_unreadable,
            is_usable=dto.is_usable,
            last_connection_ok_at=dto.last_connection_ok_at,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class ConnectionTestResponse(BaseModel):
    ok: bool
    detail: str
    # Razón social leída del ERP: la UI la propone como nombre para que
    # quien configura confirme que apuntó al cliente correcto.
    razon_social: str | None = None
    missing_tables: list[str] = []

    @classmethod
    def from_result(cls, result: ConnectionTestResult) -> ConnectionTestResponse:
        return cls(
            ok=result.ok,
            detail=result.detail,
            razon_social=result.razon_social,
            missing_tables=list(result.missing_tables),
        )


class ExportErpDatabasesResponse(BaseModel):
    """El campo `payload` es opaco: un blob cifrado con la contraseña de
    exportación. El frontend lo baja tal cual como archivo; para
    importarlo en otra instalación hace falta la misma contraseña."""

    version: int
    exported_at: datetime
    count: int
    payload: str

    @classmethod
    def from_dto(cls, dto: ExportPayloadDTO) -> ExportErpDatabasesResponse:
        return cls(
            version=1,
            exported_at=dto.exported_at,
            count=dto.count,
            payload=dto.ciphertext,
        )


class ImportRowResultResponse(BaseModel):
    code: str
    status: str
    detail: str | None = None


class ImportErpDatabasesResponse(BaseModel):
    rows: list[ImportRowResultResponse]

    @classmethod
    def from_dto(cls, dto: ImportResultDTO) -> ImportErpDatabasesResponse:
        return cls(
            rows=[
                ImportRowResultResponse(code=r.code, status=r.status, detail=r.detail)
                for r in dto.rows
            ]
        )


class AvailableDatabaseResponse(BaseModel):
    """Lo que ve un usuario no admin en el selector del chat.

    Deliberadamente sin host, puerto, usuario ni nombre de base: para
    elegir un cliente no hace falta la topología de conexión.
    """

    id: UUID
    code: str
    name: str

    @classmethod
    def from_dto(cls, dto: AvailableDatabaseDTO) -> AvailableDatabaseResponse:
        return cls(id=dto.id, code=dto.code, name=dto.name)
