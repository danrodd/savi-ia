"""Impl `ErpDatabaseRepository` con sessionmaker independiente.

Mismo patrón que `SqlAlchemyRefreshTokenRepository`: cada operación abre
su propia sesión, sin acoplarse al lifecycle de un request.

Es la **frontera del cifrado**: la entidad de dominio viaja con la
contraseña en claro, la columna la guarda cifrada, y la traducción
ocurre acá y solo acá.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import DuplicateErpDatabaseError
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.modules.erp_databases.infrastructure.persistence.models import (
    ErpDatabaseModel,
)
from app.shared.security import CredentialCipher, CredentialDecryptError

logger = logging.getLogger(__name__)


class SqlAlchemyErpDatabaseRepository(ErpDatabaseRepository):
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: CredentialCipher,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher

    # ── Lectura ──────────────────────────────────────────────────────

    async def get_by_id(self, database_id: UUID) -> ErpDatabase | None:
        async with self._sessionmaker() as session:
            stmt = select(ErpDatabaseModel).where(
                ErpDatabaseModel.id == database_id,
                ErpDatabaseModel.deleted_at.is_(None),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_by_code(self, code: str) -> ErpDatabase | None:
        async with self._sessionmaker() as session:
            # `code` ya viene normalizado a mayúsculas por el value
            # object, pero comparamos con `upper()` igual: una fila
            # sembrada a mano o migrada desde una versión anterior podría
            # no estarlo, y un login que falla por eso es indistinguible
            # de una credencial mala.
            stmt = select(ErpDatabaseModel).where(
                func.upper(ErpDatabaseModel.code) == code.strip().upper(),
                ErpDatabaseModel.deleted_at.is_(None),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_default(self) -> ErpDatabase | None:
        async with self._sessionmaker() as session:
            stmt = select(ErpDatabaseModel).where(
                ErpDatabaseModel.is_default.is_(True),
                ErpDatabaseModel.deleted_at.is_(None),
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list_all(self, *, include_inactive: bool = False) -> list[ErpDatabase]:
        async with self._sessionmaker() as session:
            stmt = select(ErpDatabaseModel).where(
                ErpDatabaseModel.deleted_at.is_(None)
            )
            if not include_inactive:
                stmt = stmt.where(ErpDatabaseModel.is_active.is_(True))
            stmt = stmt.order_by(ErpDatabaseModel.name)
            rows = (await session.execute(stmt)).scalars().all()
        return [self._to_entity(r) for r in rows]

    async def count(self) -> int:
        # Cuenta TODAS, incluidas las eliminadas: el seed no debe
        # resucitar una base que se dio de baja a propósito.
        async with self._sessionmaker() as session:
            stmt = select(func.count()).select_from(ErpDatabaseModel)
            return int((await session.execute(stmt)).scalar_one())

    # ── Escritura ────────────────────────────────────────────────────

    async def save(self, database: ErpDatabase) -> None:
        async with self._sessionmaker() as session:
            existing = await session.get(ErpDatabaseModel, database.id)
            if existing is None:
                session.add(self._to_model(database))
            else:
                self._apply(existing, database)
            try:
                await session.commit()
            except IntegrityError as e:
                # Los índices únicos parciales de `code` y `name` disparan
                # esto. Se traduce a una excepción de dominio (→ 422) en
                # lugar de dejar escapar un 500 con un mensaje de SQLite.
                await session.rollback()
                raise _as_duplicate_error(database, e) from e

    # ── Traducción ORM ↔ dominio ─────────────────────────────────────

    def _to_entity(self, row: ErpDatabaseModel) -> ErpDatabase:
        """El descifrado que falla NO se propaga.

        Se devuelve la entidad con `credentials_unreadable=True` y la
        contraseña vacía. La base queda inutilizable (`is_usable` es
        `False`) hasta que alguien re-ingrese la contraseña, pero listar
        las bases, mostrar el historial y arrancar la aplicación siguen
        funcionando.
        """
        unreadable = row.credentials_unreadable
        password = ""
        if not unreadable:
            try:
                password = self._cipher.decrypt(row.password_encrypted)
            except CredentialDecryptError:
                # Sin la contraseña en el log, obviamente. El `code`
                # alcanza para que el administrador sepa cuál re-cargar.
                logger.warning(
                    "Credenciales ilegibles para la base '%s' (%s): "
                    "ERP_CREDENTIALS_KEY no coincide. Hay que re-ingresar "
                    "la contraseña desde administración.",
                    row.code,
                    row.id,
                )
                unreadable = True

        return ErpDatabase(
            id=row.id,
            code=row.code,
            name=row.name,
            host=row.host,
            port=row.port,
            database=row.database,
            username=row.username,
            password=password,
            statement_timeout_ms=row.statement_timeout_ms,
            is_default=row.is_default,
            is_active=row.is_active,
            deleted_at=row.deleted_at,
            credentials_unreadable=unreadable,
            last_connection_ok_at=row.last_connection_ok_at,
            seed_revision=row.seed_revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_model(self, entity: ErpDatabase) -> ErpDatabaseModel:
        return ErpDatabaseModel(
            id=entity.id,
            code=entity.code,
            name=entity.name,
            host=entity.host,
            port=entity.port,
            database=entity.database,
            username=entity.username,
            password_encrypted=self._cipher.encrypt(entity.password),
            statement_timeout_ms=entity.statement_timeout_ms,
            is_default=entity.is_default,
            is_active=entity.is_active,
            deleted_at=entity.deleted_at,
            credentials_unreadable=entity.credentials_unreadable,
            last_connection_ok_at=entity.last_connection_ok_at,
            seed_revision=entity.seed_revision,
        )

    def _apply(self, row: ErpDatabaseModel, entity: ErpDatabase) -> None:
        row.code = entity.code
        row.name = entity.name
        row.host = entity.host
        row.port = entity.port
        row.database = entity.database
        row.username = entity.username
        row.statement_timeout_ms = entity.statement_timeout_ms
        row.is_default = entity.is_default
        row.is_active = entity.is_active
        row.deleted_at = entity.deleted_at
        row.last_connection_ok_at = entity.last_connection_ok_at
        row.seed_revision = entity.seed_revision
        # Contraseña vacía = conservar la que ya está. Es lo que permite
        # que el formulario de edición la deje en blanco cuando no se
        # quiere cambiar, sin tener que devolverla al cliente para que la
        # reenvíe.
        if entity.password:
            row.password_encrypted = self._cipher.encrypt(entity.password)
            row.credentials_unreadable = False
        else:
            row.credentials_unreadable = entity.credentials_unreadable


def _as_duplicate_error(
    database: ErpDatabase, error: IntegrityError
) -> DuplicateErpDatabaseError:
    """Nombra el campo en conflicto cuando el motor lo dice.

    SQLite y Postgres reportan el índice violado en el texto del error;
    si no se puede identificar, se cae a un mensaje genérico igual de
    válido.
    """
    detail = str(error.orig).lower()
    if "code" in detail:
        return DuplicateErpDatabaseError(
            f"Ya existe una base de datos con el código '{database.code}'."
        )
    if "name" in detail:
        return DuplicateErpDatabaseError(
            f"Ya existe una base de datos con el nombre '{database.name}'."
        )
    if "default" in detail:
        # No debería llegar acá: `set_default` baja la anterior primero.
        # Queda como red de seguridad del índice único de default.
        return DuplicateErpDatabaseError(
            "Ya hay otra base marcada como predeterminada."
        )
    return DuplicateErpDatabaseError(
        "Ya existe una base de datos con esos datos (código o nombre repetido)."
    )
