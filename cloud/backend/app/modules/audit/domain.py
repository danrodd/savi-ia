"""Auditoría de acciones del staff (§6 de la Fase 3): registro solo de inserción."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

# Fragmentos de nombre de campo cuyo valor jamás se guarda en `before`/`after`.
_SECRET_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "hash",
    "totp",
    "mfa_code",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "key",
)
REDACTED = "[redactado]"


def redact(value: Any) -> Any:
    """Copia de `value` con los campos sensibles reemplazados por `[redactado]`.

    Por nombre de campo y de forma recursiva: es una lista de exclusión deliberadamente
    amplia (un falso positivo oculta un dato; un falso negativo filtra un secreto).
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
            name = str(key)  # pyright: ignore[reportUnknownArgumentType]
            if any(marker in name.lower() for marker in _SECRET_MARKERS):
                out[name] = REDACTED
            else:
                out[name] = redact(item)
        return out
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


@dataclass(frozen=True)
class AuditEntry:
    id: UUID
    occurred_at: datetime
    actor_staff_id: UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    user_agent: str | None


@dataclass(frozen=True)
class RequestContext:
    """Quién y desde dónde actúa: se pasa a los casos de uso que auditan."""

    actor_staff_id: UUID | None = None
    actor_email: str | None = None
    ip: str | None = None
    user_agent: str | None = None


class AuditRepository(Protocol):
    async def add(self, entry: AuditEntry) -> None: ...

    async def list(
        self,
        *,
        actor: str | None,
        action: str | None,
        target: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        before_id: tuple[datetime, UUID] | None,
    ) -> list[AuditEntry]: ...
