"""DTOs del módulo.

**Ninguno lleva la contraseña de salida.** `ErpDatabaseDTO` es lo que
alimenta las respuestas del API, y la contraseña no sale del backend ni
en claro ni cifrada. Es una regla estructural, no una omisión: el campo
directamente no existe acá.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.erp_databases.domain.entities import ErpDatabase


@dataclass(frozen=True, slots=True)
class SaveErpDatabaseDTO:
    """Datos del formulario. La contraseña SOLO viaja de entrada.

    Vacía significa "conservar la guardada": permite editar sin
    devolverle la contraseña al cliente para que la reenvíe.
    """

    code: str
    name: str
    host: str
    port: int
    database: str
    username: str
    password: str
    statement_timeout_ms: int = 60000


@dataclass(frozen=True, slots=True)
class ErpDatabaseDTO:
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
    def from_entity(cls, entity: ErpDatabase) -> ErpDatabaseDTO:
        return cls(
            id=entity.id,
            code=entity.code,
            name=entity.name,
            host=entity.host,
            port=entity.port,
            database=entity.database,
            username=entity.username,
            statement_timeout_ms=entity.statement_timeout_ms,
            is_default=entity.is_default,
            is_active=entity.is_active,
            credentials_unreadable=entity.credentials_unreadable,
            is_usable=entity.is_usable,
            last_connection_ok_at=entity.last_connection_ok_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


@dataclass(frozen=True, slots=True)
class AvailableDatabaseDTO:
    """Lo mínimo para el selector del chat: id y nombre.

    Sin host, puerto, usuario ni nombre de base — un usuario no admin no
    necesita la topología de conexión para elegir un cliente.
    """

    id: UUID
    code: str
    name: str
