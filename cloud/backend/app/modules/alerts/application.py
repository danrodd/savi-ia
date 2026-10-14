"""Motor de alertas y acciones sobre ellas (§5.2).

No abren transacciones: lo hace el llamador (el job o la ruta HTTP).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from app.modules.alerts.domain import (
    LIVE_STATUSES,
    SYSTEM_ACTOR,
    Alert,
    AlertAlreadyResolved,
    AlertNotFound,
    AlertNotifier,
    AlertRepository,
    AlertRuleNotFound,
    AlertRuleRepository,
    AlertStatus,
    Finding,
    InvalidAlertRule,
    RuleConfig,
    Severity,
)
from app.modules.alerts.rules import EVALUATORS, RULES, RULES_BY_CODE, EvalContext
from app.modules.audit.application import AuditRecorder
from app.modules.audit.domain import RequestContext
from app.shared.clock import Clock

MAX_NOTE_LENGTH = 500


class NoopAlertNotifier:
    """Hasta que exista un canal externo (correo, chat), las alertas viven solo en la consola."""

    async def alert_opened(self, alert: Alert) -> None:
        return None


async def load_rule_configs(rules: AlertRuleRepository) -> list[RuleConfig]:
    overrides = await rules.overrides()
    configs: list[RuleConfig] = []
    for definition in RULES:
        enabled, threshold, severity = overrides.get(
            definition.code, (True, definition.threshold, definition.severity)
        )
        configs.append(RuleConfig(definition, enabled, threshold, severity))
    return configs


@dataclass(frozen=True)
class EvaluationResult:
    opened: int
    updated: int
    resolved: int


class EvaluateAlertsUseCase:
    def __init__(
        self,
        alerts: AlertRepository,
        rules: AlertRuleRepository,
        notifier: AlertNotifier,
        clock: Clock,
    ) -> None:
        self._alerts = alerts
        self._rules = rules
        self._notifier = notifier
        self._clock = clock

    async def execute(self, ctx: EvalContext) -> EvaluationResult:
        now = self._clock()
        configs = {c.code: c for c in await load_rule_configs(self._rules)}

        findings: dict[str, Finding] = {}
        for code, cfg in configs.items():
            if cfg.enabled:
                for finding in EVALUATORS[code](ctx, cfg):
                    findings[finding.key] = finding

        live = {a.dedup_key: a for a in await self._alerts.list_live()}
        opened = updated = resolved = 0

        for key, finding in findings.items():
            existing = live.get(key)
            if existing is None:
                alert = Alert(
                    id=uuid4(),
                    rule_code=finding.rule_code,
                    severity=finding.severity,
                    client_id=finding.client_id,
                    instance_id=finding.instance_id,
                    status=AlertStatus.OPEN,
                    details=finding.details,
                    opened_at=now,
                    dedup_key=key,
                )
                await self._alerts.add(alert)
                await self._notifier.alert_opened(alert)
                opened += 1
            elif existing.severity != finding.severity or existing.details != finding.details:
                await self._alerts.save(
                    replace(existing, severity=finding.severity, details=finding.details)
                )
                updated += 1

        for key, alert in live.items():
            if key in findings:
                continue
            cfg = configs.get(alert.rule_code)
            if cfg is None or not cfg.enabled:
                note = "La regla ya no está activa."
            elif cfg.definition.auto_resolve:
                note = "La condición dejó de cumplirse."
            else:
                continue  # se resuelve a mano
            await self._alerts.save(
                replace(
                    alert,
                    status=AlertStatus.RESOLVED,
                    resolved_at=now,
                    resolved_by=SYSTEM_ACTOR,
                    resolution_note=note,
                )
            )
            resolved += 1
        return EvaluationResult(opened=opened, updated=updated, resolved=resolved)


@dataclass(frozen=True)
class AlertActions:
    alerts: AlertRepository
    rules: AlertRuleRepository
    audit: AuditRecorder
    clock: Clock

    async def _get(self, alert_id: UUID) -> Alert:
        alert = await self.alerts.get(alert_id)
        if alert is None:
            raise AlertNotFound("No existe la alerta.")
        return alert

    async def acknowledge(self, alert_id: UUID, ctx: RequestContext) -> Alert:
        alert = await self._get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise AlertAlreadyResolved("La alerta ya está resuelta.")
        if alert.status is AlertStatus.ACKNOWLEDGED:
            return alert
        updated = replace(
            alert,
            status=AlertStatus.ACKNOWLEDGED,
            acknowledged_at=self.clock(),
            acknowledged_by=ctx.actor_email,
        )
        await self.alerts.save(updated)
        await self.audit.record(
            ctx,
            "alert.acknowledge",
            target_type="alert",
            target_id=str(alert_id),
            before={"status": alert.status.value},
            after={"status": updated.status.value},
        )
        return updated

    async def resolve(self, alert_id: UUID, note: str, ctx: RequestContext) -> Alert:
        alert = await self._get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise AlertAlreadyResolved("La alerta ya está resuelta.")
        clean = note.strip()
        if len(clean) > MAX_NOTE_LENGTH:
            raise InvalidAlertRule(f"La nota admite hasta {MAX_NOTE_LENGTH} caracteres.")
        updated = replace(
            alert,
            status=AlertStatus.RESOLVED,
            resolved_at=self.clock(),
            resolved_by=ctx.actor_email,
            resolution_note=clean or None,
        )
        await self.alerts.save(updated)
        await self.audit.record(
            ctx,
            "alert.resolve",
            target_type="alert",
            target_id=str(alert_id),
            before={"status": alert.status.value},
            after={"status": updated.status.value, "resolution_note": updated.resolution_note},
        )
        return updated

    async def configure_rule(
        self,
        code: str,
        *,
        enabled: bool | None,
        threshold: float | None,
        threshold_given: bool,
        severity: Severity | None,
        ctx: RequestContext,
    ) -> RuleConfig:
        if code not in RULES_BY_CODE:
            raise AlertRuleNotFound("No existe la regla.")
        current = next(c for c in await load_rule_configs(self.rules) if c.code == code)
        new_threshold = current.threshold
        if threshold_given:
            if current.definition.threshold is None:
                raise InvalidAlertRule("Esta regla no usa umbral.")
            if threshold is None or threshold <= 0:
                raise InvalidAlertRule("El umbral tiene que ser mayor que cero.")
            new_threshold = threshold
        updated = replace(
            current,
            enabled=current.enabled if enabled is None else enabled,
            threshold=new_threshold,
            severity=severity or current.severity,
        )
        await self.rules.set(
            code, enabled=updated.enabled, threshold=updated.threshold, severity=updated.severity
        )
        await self.audit.record(
            ctx,
            "alert_rule.update",
            target_type="alert_rule",
            target_id=code,
            before={
                "enabled": current.enabled,
                "threshold": current.threshold,
                "severity": current.severity.value,
            },
            after={
                "enabled": updated.enabled,
                "threshold": updated.threshold,
                "severity": updated.severity.value,
            },
        )
        return updated


__all__ = [
    "LIVE_STATUSES",
    "AlertActions",
    "EvaluateAlertsUseCase",
    "EvaluationResult",
    "NoopAlertNotifier",
    "load_rule_configs",
]
