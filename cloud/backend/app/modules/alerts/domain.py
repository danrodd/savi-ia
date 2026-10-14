"""Alertas (§5 de la Fase 3): reglas, hallazgos y estado de cada alerta."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from app.shared.errors import DomainError


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# Estados en los que una alerta "sigue viva": no se abre una segunda igual.
LIVE_STATUSES = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)
SYSTEM_ACTOR = "sistema"


@dataclass(frozen=True)
class RuleDefinition:
    code: str
    title: str
    description: str
    severity: Severity
    # Umbral por defecto y su unidad (texto para la consola). `None` si la regla no usa umbral.
    threshold: float | None
    threshold_unit: str | None
    auto_resolve: bool


@dataclass(frozen=True)
class RuleConfig:
    """Definición con los ajustes que el administrador cambió."""

    definition: RuleDefinition
    enabled: bool
    threshold: float | None
    severity: Severity

    @property
    def code(self) -> str:
        return self.definition.code


@dataclass(frozen=True)
class Finding:
    """Algo que la regla encontró en esta evaluación."""

    rule_code: str
    severity: Severity
    client_id: UUID
    instance_id: UUID | None
    details: dict[str, Any] = field(default_factory=lambda: {})

    @property
    def key(self) -> str:
        return dedup_key(self.rule_code, self.client_id, self.instance_id)


def dedup_key(rule_code: str, client_id: UUID, instance_id: UUID | None) -> str:
    return f"{rule_code}:{client_id}:{instance_id or '-'}"


@dataclass(frozen=True)
class Alert:
    id: UUID
    rule_code: str
    severity: Severity
    client_id: UUID
    instance_id: UUID | None
    status: AlertStatus
    details: dict[str, Any]
    opened_at: datetime
    dedup_key: str
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None


class AlertNotFound(DomainError):
    code = "alert_not_found"


class AlertRuleNotFound(DomainError):
    code = "alert_rule_not_found"


class InvalidAlertRule(DomainError):
    code = "invalid_alert_rule"


class AlertAlreadyResolved(DomainError):
    code = "alert_already_resolved"


class AlertRepository(Protocol):
    async def add(self, alert: Alert) -> None: ...

    async def get(self, alert_id: UUID) -> Alert | None: ...

    async def save(self, alert: Alert) -> None: ...

    async def list_live(self) -> list[Alert]: ...

    async def list(
        self,
        *,
        status: AlertStatus | None,
        severity: Severity | None,
        client_id: UUID | None,
        limit: int,
    ) -> list[Alert]: ...

    async def count_open_by_severity(self) -> dict[Severity, int]: ...


class AlertRuleRepository(Protocol):
    async def overrides(self) -> dict[str, tuple[bool, float | None, Severity]]: ...

    async def set(
        self, code: str, *, enabled: bool, threshold: float | None, severity: Severity
    ) -> None: ...


class AlertNotifier(Protocol):
    """Puerto para avisar fuera de la consola (correo, chat). Hoy: sin implementación real."""

    async def alert_opened(self, alert: Alert) -> None: ...
