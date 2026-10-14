"""Segundo factor (TOTP) de un usuario del ERP.

La identidad es el par `(erp_database_id, user_id)`: el `idUsuario` se repite entre bases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserTotp:
    erp_database_id: UUID
    user_id: int
    user_login: str
    # En claro en memoria (el repositorio descifra). `None` si no se pudo descifrar: ver
    # `unreadable`.
    secret: str | None
    # `None` mientras la configuración está pendiente (todavía no se confirmó un código).
    enabled_at: datetime | None
    # Último paso de 30 s aceptado: un código no se acepta dos veces.
    last_step: int
    # El secreto está pero no se puede descifrar con la clave actual del servidor.
    unreadable: bool = False

    @property
    def enabled(self) -> bool:
        return self.enabled_at is not None
