"""Casos de uso de administración de las bases del ERP.

Reglas que se aplican acá y no en la capa HTTP, porque son del dominio:

- **Test de conexión obligatorio antes de persistir** (D5). Si falla, no
  se guarda nada.
- **La base default no se puede eliminar ni desactivar** sin designar
  otra antes: quedarse sin default deja el login sin a dónde ir.
- **Baja lógica siempre**: `conversations.erp_database_id` es una FK y el
  historial tiene que seguir siendo legible.
- **Invalidar el engine tras cualquier cambio**: sin eso, editar una
  contraseña no tiene efecto hasta reiniciar el proceso.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.modules.erp_databases.application.dtos import (
    ErpDatabaseDTO,
    SaveErpDatabaseDTO,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import (
    ErpDatabaseNotFoundError,
    ErpDatabaseUnavailableError,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.modules.erp_databases.domain.interfaces.connection_tester import (
    ConnectionTester,
    ConnectionTestResult,
)
from app.modules.erp_databases.domain.value_objects import normalize_code
from app.modules.erp_databases.infrastructure.engine_registry import ErpEngineRegistry
from app.shared.exceptions import ValidationError


class ManageErpDatabasesUseCase:
    def __init__(
        self,
        repository: ErpDatabaseRepository,
        tester: ConnectionTester,
        registry: ErpEngineRegistry,
    ) -> None:
        self._repository = repository
        self._tester = tester
        self._registry = registry

    # ── Lectura ──────────────────────────────────────────────────────

    async def list(self, *, include_inactive: bool = False) -> list[ErpDatabaseDTO]:
        databases = await self._repository.list_all(include_inactive=include_inactive)
        return [ErpDatabaseDTO.from_entity(d) for d in databases]

    async def get(self, database_id: UUID) -> ErpDatabaseDTO:
        return ErpDatabaseDTO.from_entity(await self._require(database_id))

    # ── Prueba de conexión suelta ────────────────────────────────────

    async def test_connection(
        self, dto: SaveErpDatabaseDTO, *, database_id: UUID | None = None
    ) -> ConnectionTestResult:
        """El botón "probar conexión" del formulario, sin persistir nada.

        Con `database_id` re-testea una guardada: permite dejar la
        contraseña vacía y reutilizar la almacenada, sin devolverla nunca
        al cliente para que la reenvíe.
        """
        candidate = await self._candidate(dto, database_id)
        return await self._tester.test(candidate)

    # ── Escritura ────────────────────────────────────────────────────

    async def create(self, dto: SaveErpDatabaseDTO) -> ErpDatabaseDTO:
        if not dto.password:
            raise ValidationError(
                "La contraseña es obligatoria al registrar una base nueva."
            )
        candidate = await self._candidate(dto, None)
        await self._ensure_connects(candidate)

        # La primera base registrada queda como default: si no, no habría
        # ninguna y el login no tendría a dónde ir.
        if await self._repository.get_default() is None:
            candidate.is_default = True

        await self._repository.save(candidate)
        return ErpDatabaseDTO.from_entity(candidate)

    async def update(self, database_id: UUID, dto: SaveErpDatabaseDTO) -> ErpDatabaseDTO:
        existing = await self._require(database_id)
        candidate = await self._candidate(dto, database_id)
        candidate.id = existing.id
        candidate.is_default = existing.is_default
        candidate.is_active = existing.is_active
        # Sin esto una edición manual borraría la revisión y el próximo
        # arranque la pisaría con lo que diga el `.env`.
        candidate.seed_revision = existing.seed_revision

        await self._ensure_connects(candidate)
        await self._repository.save(candidate)
        # Sin esto, cambiar la contraseña o el host no tendría efecto
        # hasta reiniciar el proceso.
        await self._registry.invalidate(database_id)
        return ErpDatabaseDTO.from_entity(candidate)

    async def set_default(self, database_id: UUID) -> ErpDatabaseDTO:
        target = await self._require(database_id)
        if not target.is_active:
            raise ValidationError(
                "No se puede marcar como predeterminada una base desactivada."
            )

        current = await self._repository.get_default()
        if current is not None and current.id != target.id:
            # Se baja la anterior primero: el índice único parcial sobre
            # `is_default` rechazaría tener dos a la vez.
            current.is_default = False
            await self._repository.save(current)

        target.is_default = True
        await self._repository.save(target)
        return ErpDatabaseDTO.from_entity(target)

    async def activate(self, database_id: UUID) -> ErpDatabaseDTO:
        database = await self._require(database_id)
        database.is_active = True
        await self._repository.save(database)
        return ErpDatabaseDTO.from_entity(database)

    async def deactivate(self, database_id: UUID) -> ErpDatabaseDTO:
        database = await self._require(database_id)
        self._forbid_if_default(database, "desactivar")
        database.is_active = False
        await self._repository.save(database)
        # Los turnos en curso contra esta base tienen que cortarse: dejar
        # el engine vivo permitiría seguir consultando una base dada de
        # baja hasta que expire el pool.
        await self._registry.invalidate(database_id)
        return ErpDatabaseDTO.from_entity(database)

    async def soft_delete(self, database_id: UUID) -> None:
        database = await self._repository.get_by_id(database_id)
        if database is None:
            # Idempotente: borrar dos veces no es un error.
            return
        self._forbid_if_default(database, "eliminar")
        database.soft_delete()
        await self._repository.save(database)
        await self._registry.invalidate(database_id)

    # ── Interno ──────────────────────────────────────────────────────

    async def _require(self, database_id: UUID) -> ErpDatabase:
        database = await self._repository.get_by_id(database_id)
        if database is None:
            raise ErpDatabaseNotFoundError(
                "La base de datos del ERP indicada no existe."
            )
        return database

    def _forbid_if_default(self, database: ErpDatabase, action: str) -> None:
        if database.is_default:
            raise ValidationError(
                f"No se puede {action} la base predeterminada. Marcá otra como "
                "predeterminada primero."
            )

    async def _candidate(
        self, dto: SaveErpDatabaseDTO, database_id: UUID | None
    ) -> ErpDatabase:
        """Arma la entidad a probar/guardar desde el DTO del formulario.

        Contraseña vacía = conservar la guardada. Es lo que permite editar
        sin que la contraseña viaje al cliente y vuelva.
        """
        password = dto.password
        if not password and database_id is not None:
            stored = await self._require(database_id)
            if stored.credentials_unreadable:
                raise ValidationError(
                    "Las credenciales guardadas no se pueden leer. Ingresá la "
                    "contraseña de nuevo."
                )
            password = stored.password

        return ErpDatabase(
            code=normalize_code(dto.code),
            name=dto.name.strip(),
            host=dto.host.strip(),
            port=dto.port,
            database=dto.database.strip(),
            username=dto.username.strip(),
            password=password,
            statement_timeout_ms=dto.statement_timeout_ms,
        )

    async def _ensure_connects(self, candidate: ErpDatabase) -> None:
        """D5: nunca se persiste una conexión que no se probó.

        Sin esto se puede guardar un host mal escrito, y el error
        aparecería recién a mitad de un chat.
        """
        result = await self._tester.test(candidate)
        if not result.ok:
            raise ValidationError(result.detail)
        candidate.last_connection_ok_at = datetime.now(UTC)


__all__ = ["ErpDatabaseUnavailableError", "ManageErpDatabasesUseCase"]
