from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.modules.audit.domain import AuditEntry, AuditRepository, RequestContext, redact
from app.shared.clock import Clock


class AuditRecorder:
    """Escribe en la **misma** sesión (transacción) que la acción auditada.

    Si la inserción falla, falla la acción: no hay cambios de estado sin rastro.
    """

    def __init__(self, repository: AuditRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def record(
        self,
        context: RequestContext,
        action: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        await self._repository.add(
            AuditEntry(
                id=uuid4(),
                occurred_at=self._clock(),
                actor_staff_id=context.actor_staff_id,
                actor_email=context.actor_email,
                action=action,
                target_type=target_type,
                target_id=target_id,
                before=redact(before) if before is not None else None,
                after=redact(after) if after is not None else None,
                ip=context.ip,
                user_agent=(context.user_agent or "")[:256] or None,
            )
        )
