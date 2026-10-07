"""Entidad `ErpDatabase` — una conexión registrada a la BD de un cliente.

Es **independiente** del ORM: el repositorio la construye traduciendo
las columnas. La contraseña vive acá **en claro** porque es lo que el
registry necesita para armar la URL de conexión; el cifrado ocurre en el
borde de persistencia (`CredentialCipher`), no en el dominio.

Nada de esta entidad se serializa hacia el cliente tal cual: los
responses se arman desde DTOs que no incluyen `password`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ErpDatabase:
    id: UUID = field(default_factory=uuid4)
    # Identificador corto del cliente: lo que va después del `@` en el
    # login. Ver `value_objects.database_code`.
    code: str = ""
    # Nombre visible. Se propone la razón social leída del ERP, editable.
    name: str = ""
    host: str = ""
    port: int = 5432
    database: str = ""
    username: str = ""
    # En claro. Se cifra al persistir y se descifra al leer.
    password: str = ""
    statement_timeout_ms: int = 60000
    is_default: bool = False
    is_active: bool = True
    deleted_at: datetime | None = None
    # `True` cuando el descifrado falló: la clave cambió o se perdió.
    # La base queda inutilizable hasta re-ingresar la contraseña, pero la
    # aplicación arranca igual. Ver `FernetCredentialCipher`.
    credentials_unreadable: bool = False
    last_connection_ok_at: datetime | None = None
    # Revisión del `.env` (`ERP_SEED_REVISION`) con la que se sembró o
    # actualizó esta base. Solo la usa el seed de arranque.
    seed_revision: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_usable(self) -> bool:
        """`True` si se puede abrir una conexión y consultar contra ella.

        Las tres condiciones son independientes: una base eliminada, una
        desactivada y una con credenciales ilegibles se bloquean por
        motivos distintos pero el efecto para el chat es el mismo.
        """
        return (
            not self.is_deleted
            and self.is_active
            and not self.credentials_unreadable
        )

    @property
    def url(self) -> str:
        """URL asyncpg para SQLAlchemy.

        `quote` sobre usuario y contraseña: una contraseña con `@`, `/`
        o `:` — perfectamente válida en Postgres — rompería el parseo de
        la URL y produciría un error de conexión imposible de diagnosticar
        desde el mensaje.
        """
        user = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    def soft_delete(self) -> None:
        self.deleted_at = _utc_now()
        self.updated_at = self.deleted_at
