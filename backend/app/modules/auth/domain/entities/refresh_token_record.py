"""Registro de un refresh token activo.

Persistido en `agent_db.refresh_token` para soportar revocación real
en `logout` y para auditar la actividad de tokens (cuántos hay vivos
por usuario, cuándo se revocan).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RefreshTokenRecord:
    # `jti` del JWT — único por token emitido.
    jti: UUID
    # `idUsuario` del ERP (dueño del token).
    user_id: int
    user_login: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
