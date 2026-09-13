"""Requests del CRUD de bases del ERP.

La contraseña **solo** viaja de entrada. Ningún response la incluye, ni
en claro ni cifrada.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.erp_databases.application.dtos import SaveErpDatabaseDTO


class SaveErpDatabaseRequest(BaseModel):
    # El patrón excluye el `@` por construcción: es lo que hace que el
    # `rsplit` del login calificado nunca sea ambiguo.
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=120)
    # Vacía al editar = conservar la guardada. Obligatoria al crear, pero
    # esa regla es del caso de uso: acá no se puede distinguir.
    password: str = Field(default="")
    statement_timeout_ms: int = Field(default=60000, ge=1000, le=600000)

    def to_dto(self) -> SaveErpDatabaseDTO:
        return SaveErpDatabaseDTO(
            code=self.code,
            name=self.name,
            host=self.host,
            port=self.port,
            database=self.database,
            username=self.username,
            password=self.password,
            statement_timeout_ms=self.statement_timeout_ms,
        )
