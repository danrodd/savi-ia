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
    # `idUsuario` del ERP (dueño del token). NO es único entre bases:
    # va siempre acompañado de `erp_database_id`.
    user_id: int
    # Base del ERP donde vive el dueño. Sin ella, dos usuarios con el
    # mismo `idUsuario` en clientes distintos compartirían revocaciones.
    erp_database_id: UUID
    user_login: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
