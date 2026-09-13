"""Exportar/importar la configuración de bases del ERP entre instalaciones.

Pensado para un call center: varios agentes, cada uno con su propia
instalación de escritorio, necesitan la MISMA lista de clientes
registrados. Sin esto, cargar un cliente nuevo (o cambiarle el host)
significa repetir el alta a mano en cada máquina.

Reutiliza `ManageErpDatabasesUseCase.create`/`update` fila por fila: así
el import pasa por el mismo camino que el alta manual desde el panel —
se prueba la conexión antes de persistir (D5) y la contraseña se cifra
con la `ERP_CREDENTIALS_KEY` de ESTA instalación (D4), nunca con la de
origen, que ni siquiera viaja en el archivo.

El import es best-effort por fila, no atómico: los agentes pueden estar
en redes distintas, y que un cliente no sea alcanzable desde una
máquina no debe impedir importar el resto.

Los modelos `_ExportRow`/`_ExportFile` son Pydantic y no dataclasses a
propósito, a diferencia del resto de los DTOs del módulo: acá SÍ hace
falta validar en runtime un JSON que viene de un archivo externo — el
mismo motivo por el que `requests/` usa Pydantic y `application/dtos`
no.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.modules.erp_databases.application.dtos import (
    ExportPayloadDTO,
    ImportResultDTO,
    ImportRowResultDTO,
    SaveErpDatabaseDTO,
)
from app.modules.erp_databases.application.use_cases.manage_erp_databases import (
    ManageErpDatabasesUseCase,
)
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.exceptions import InvalidExportPassphraseError
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.modules.erp_databases.domain.value_objects import normalize_code
from app.modules.erp_databases.infrastructure.security.export_cipher import (
    decrypt_with_passphrase,
    encrypt_with_passphrase,
)
from app.shared.exceptions import ValidationError

_FORMAT_VERSION = 1


class _ExportRow(BaseModel):
    """Una fila del archivo. SÍ lleva la contraseña en claro — viaja
    dentro del sobre cifrado con la contraseña de exportación, nunca sin
    cifrar. Es lo único que permite que otra instalación pueda volver a
    probar la conexión y cifrarla con SU propia `ERP_CREDENTIALS_KEY`."""

    code: str
    name: str
    host: str
    port: int
    database: str
    username: str
    password: str
    statement_timeout_ms: int = 60000
    is_default: bool = False


class _ExportFile(BaseModel):
    version: int
    # `dict` y no `list[_ExportRow]`: una fila individual mal formada no
    # debe tumbar la lectura del archivo entero — se valida fila por fila
    # en `import_` para poder reportarla como `failed` y seguir con el
    # resto.
    databases: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class ExportImportErpDatabasesUseCase:
    def __init__(
        self,
        repository: ErpDatabaseRepository,
        manager: ManageErpDatabasesUseCase,
    ) -> None:
        self._repository = repository
        self._manager = manager

    async def export(self, passphrase: str) -> ExportPayloadDTO:
        if not passphrase:
            raise ValidationError("La contraseña de exportación es obligatoria.")

        # Solo activas: una desactivada no le sirve a otro agente para
        # trabajar, y replicar ese estado agregaría un camino de import
        # (reactivar/desactivar) que nadie pidió. Se administra a mano si
        # hace falta. Las de credenciales ilegibles se omiten: no hay
        # contraseña que exportar.
        databases: list[ErpDatabase] = [
            d
            for d in await self._repository.list_all(include_inactive=False)
            if not d.credentials_unreadable
        ]
        rows = [
            _ExportRow(
                code=d.code,
                name=d.name,
                host=d.host,
                port=d.port,
                database=d.database,
                username=d.username,
                password=d.password,
                statement_timeout_ms=d.statement_timeout_ms,
                is_default=d.is_default,
            )
            for d in databases
        ]
        file_payload = _ExportFile(
            version=_FORMAT_VERSION, databases=[r.model_dump() for r in rows]
        )
        ciphertext = encrypt_with_passphrase(file_payload.model_dump_json(), passphrase)
        return ExportPayloadDTO(
            exported_at=datetime.now(UTC), count=len(rows), ciphertext=ciphertext
        )

    async def import_(self, passphrase: str, ciphertext: str) -> ImportResultDTO:
        if not passphrase:
            raise ValidationError("La contraseña de exportación es obligatoria.")

        plaintext = decrypt_with_passphrase(ciphertext, passphrase)
        try:
            file_payload = _ExportFile.model_validate(json.loads(plaintext))
        except (json.JSONDecodeError, PydanticValidationError) as e:
            raise InvalidExportPassphraseError(
                "No se pudo leer el archivo: el contenido no es válido."
            ) from e
        if file_payload.version != _FORMAT_VERSION:
            raise ValidationError(
                "El archivo es de una versión de exportación no soportada."
            )

        rows: list[ImportRowResultDTO] = []
        default_code: str | None = None
        for raw in file_payload.databases:
            code = str(raw.get("code") or "?")
            try:
                row = _ExportRow.model_validate(raw)
                code = normalize_code(row.code)
            except (PydanticValidationError, ValueError) as e:
                rows.append(
                    ImportRowResultDTO(
                        code=code, status="failed", detail=f"Fila inválida: {e}"
                    )
                )
                continue

            dto = SaveErpDatabaseDTO(
                code=code,
                name=row.name,
                host=row.host,
                port=row.port,
                database=row.database,
                username=row.username,
                password=row.password,
                statement_timeout_ms=row.statement_timeout_ms,
            )
            try:
                existing = await self._repository.get_by_code(code)
                if existing is None:
                    await self._manager.create(dto)
                    rows.append(ImportRowResultDTO(code=code, status="created"))
                else:
                    await self._manager.update(existing.id, dto)
                    rows.append(ImportRowResultDTO(code=code, status="updated"))
                if row.is_default:
                    default_code = code
            except ValidationError as e:
                # No aborta el resto: otro agente puede no alcanzar este
                # cliente en particular por su red, y el resto sigue.
                rows.append(ImportRowResultDTO(code=code, status="failed", detail=str(e)))

        if default_code is not None:
            target = await self._repository.get_by_code(default_code)
            if target is not None and target.is_usable:
                await self._manager.set_default(target.id)

        return ImportResultDTO(rows=rows)


__all__ = ["ExportImportErpDatabasesUseCase"]
