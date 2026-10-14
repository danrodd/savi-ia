"""Reglas de alerta (§5.1). Funciones puras sobre un contexto ya cargado: fáciles de probar."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.alerts.domain import Finding, RuleConfig, RuleDefinition, Severity
from app.modules.clients.domain import Client, ClientStatus
from app.modules.console.queries import is_online, is_outdated
from app.modules.instances.domain import FINGERPRINT_MISMATCH, Instance, InstanceStatus
from app.shared.clock import as_utc

ONE_DAY = timedelta(days=1)

RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        "instance_offline",
        "Instancia sin conexión",
        "Una instancia activa no habla con Cloud hace más del umbral. "
        "Pasa a crítica después de 24 horas.",
        Severity.WARNING,
        60,
        "minutos",
        True,
    ),
    RuleDefinition(
        "instance_fingerprint_mismatch",
        "Huella de instancia distinta",
        "La instancia informó otra huella (posible copia o reinstalación): quedó suspendida "
        "hasta que alguien confirme que es la misma máquina o la revoque.",
        Severity.CRITICAL,
        None,
        None,
        True,
    ),
    RuleDefinition(
        "sync_stalled",
        "Envío de datos detenido",
        "Una instancia en línea con actividad no avanza la marca de uno de sus envíos "
        "hace más del umbral.",
        Severity.WARNING,
        6,
        "horas",
        True,
    ),
    RuleDefinition(
        "contract_rejected",
        "Contrato rechazado",
        "Cloud rechazó el formato de los datos de la instancia: es un error de versión "
        "entre las dos puntas.",
        Severity.CRITICAL,
        None,
        None,
        True,
    ),
    RuleDefinition(
        "clock_skew",
        "Reloj desfasado",
        "La hora de la instancia difiere de la de Cloud más que el umbral.",
        Severity.WARNING,
        300,
        "segundos",
        True,
    ),
    RuleDefinition(
        "error_rate_spike",
        "Pico de errores",
        "La tasa de error del día supera el umbral (con al menos 20 turnos).",
        Severity.WARNING,
        0.15,
        "fracción de turnos",
        True,
    ),
    RuleDefinition(
        "cost_spike",
        "Pico de costo",
        "El costo del día supera 3 veces la mediana de los 14 días previos (mínimo USD 5). "
        "Se resuelve a mano.",
        Severity.WARNING,
        3,
        "veces la mediana",
        False,
    ),
    RuleDefinition(
        "instance_warning",
        "Aviso técnico de la instancia",
        "La instancia informa un problema propio: certificado vencido, sin proveedor de IA, "
        "credenciales ilegibles o sesión local en un servidor.",
        Severity.CRITICAL,
        None,
        None,
        True,
    ),
    RuleDefinition(
        "instance_outdated",
        "Instancia desactualizada",
        "Su versión es menor que la última publicada hace más de 30 días.",
        Severity.INFO,
        30,
        "días",
        True,
    ),
    RuleDefinition(
        "no_usage",
        "Sin uso",
        "Un cliente activo con instancias en línea no registra turnos en 14 días.",
        Severity.INFO,
        14,
        "días",
        True,
    ),
)

RULES_BY_CODE: dict[str, RuleDefinition] = {r.code: r for r in RULES}

# Avisos del heartbeat que cuentan como problema técnico (los propios de SAVI y los de la spec).
INSTANCE_WARNING_CODES = frozenset(
    {
        "cert_expired",
        "no_llm_provider",
        "local_session_in_server",
        "llm_unusable",
        "credentials_unreadable",
    }
)
COST_SPIKE_MIN_USD = Decimal(5)
ERROR_RATE_MIN_TURNS = 20
ESCALATION_AFTER = ONE_DAY
CRITICAL_OFFLINE_AFTER = ONE_DAY
CLOCK_SKEW_FALLBACK = 300


@dataclass(frozen=True)
class DayStats:
    turns: int = 0
    errors: int = 0
    cost_usd: Decimal = Decimal(0)


@dataclass(frozen=True)
class EvalContext:
    now: datetime
    today: date  # día calendario en America/Bogota
    clients: dict[UUID, Client]
    instances: list[Instance]
    # client_id -> día -> estadísticas (últimos 15 días, hoy incluido)
    daily: dict[UUID, dict[date, DayStats]] = field(default_factory=lambda: {})
    latest_version: str | None = None
    latest_published_at: datetime | None = None


def _live_instances(ctx: EvalContext) -> list[Instance]:
    """Instancias vigentes de clientes activos (una suspendida por el cliente no alerta)."""
    out: list[Instance] = []
    for instance in ctx.instances:
        client = ctx.clients.get(instance.client_id)
        if client is None or client.status is not ClientStatus.ACTIVE:
            continue
        if instance.status is InstanceStatus.REVOKED:
            continue
        out.append(instance)
    return out


def _sync_info(instance: Instance) -> dict[str, Any]:
    sync: dict[str, Any] = (instance.last_heartbeat or {}).get("sync") or {}
    return sync


def _watermarks(instance: Instance) -> dict[str, datetime]:
    streams: dict[str, Any] = _sync_info(instance).get("streams") or {}
    marks: dict[str, datetime] = {}
    for name, info in streams.items():
        data: dict[str, Any] = info or {}
        raw = data.get("watermark_at")
        if isinstance(raw, str):
            try:
                marks[name] = as_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
            except ValueError:
                continue
    return marks


def _finding(
    cfg: RuleConfig,
    instance: Instance | None,
    client_id: UUID,
    details: dict[str, Any],
    severity: Severity | None = None,
) -> Finding:
    return Finding(
        rule_code=cfg.code,
        severity=severity or cfg.severity,
        client_id=client_id,
        instance_id=instance.id if instance else None,
        details=details,
    )


def instance_offline(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    threshold = timedelta(minutes=cfg.threshold or 60)
    out: list[Finding] = []
    for i in _live_instances(ctx):
        if i.status is not InstanceStatus.ACTIVE:
            continue
        # Sin ningún contacto todavía: se cuenta desde que se vinculó.
        since = i.last_seen_at or i.enrolled_at
        silent = ctx.now - since
        if silent <= threshold:
            continue
        severity = Severity.CRITICAL if silent > CRITICAL_OFFLINE_AFTER else cfg.severity
        out.append(
            _finding(
                cfg,
                i,
                i.client_id,
                {"instance": i.name, "silent_minutes": int(silent.total_seconds() // 60)},
                severity,
            )
        )
    return out


def instance_fingerprint_mismatch(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    return [
        _finding(cfg, i, i.client_id, {"instance": i.name})
        for i in _live_instances(ctx)
        if i.status is InstanceStatus.SUSPENDED and i.status_reason == FINGERPRINT_MISMATCH
    ]


def sync_stalled(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    limit = timedelta(hours=cfg.threshold or 6)
    out: list[Finding] = []
    for i in _live_instances(ctx):
        if i.status is not InstanceStatus.ACTIVE or not is_online(i.last_seen_at, ctx.now):
            continue
        sessions = (i.last_heartbeat or {}).get("active_sessions") or 0
        if not sessions:
            continue
        stalled = {
            name: int((ctx.now - mark).total_seconds() // 3600)
            for name, mark in _watermarks(i).items()
            if ctx.now - mark > limit
        }
        if stalled:
            out.append(_finding(cfg, i, i.client_id, {"instance": i.name, "streams": stalled}))
    return out


def contract_rejected(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    return [
        _finding(cfg, i, i.client_id, {"instance": i.name})
        for i in _live_instances(ctx)
        if _sync_info(i).get("last_error") == "contract_rejected"
    ]


def clock_skew(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    limit = cfg.threshold or CLOCK_SKEW_FALLBACK
    return [
        _finding(cfg, i, i.client_id, {"instance": i.name, "skew_seconds": i.clock_skew_seconds})
        for i in _live_instances(ctx)
        if i.clock_skew_seconds is not None and abs(i.clock_skew_seconds) > limit
    ]


def error_rate_spike(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    limit = cfg.threshold if cfg.threshold is not None else 0.15
    out: list[Finding] = []
    for client_id, client in ctx.clients.items():
        if client.status is not ClientStatus.ACTIVE:
            continue
        today = ctx.daily.get(client_id, {}).get(ctx.today)
        if today is None or today.turns < ERROR_RATE_MIN_TURNS:
            continue
        rate = today.errors / today.turns
        if rate > limit:
            out.append(
                Finding(
                    cfg.code,
                    cfg.severity,
                    client_id,
                    None,
                    {"turns": today.turns, "errors": today.errors, "rate": round(rate, 4)},
                )
            )
    return out


def cost_spike(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    factor = Decimal(str(cfg.threshold if cfg.threshold is not None else 3))
    out: list[Finding] = []
    for client_id, client in ctx.clients.items():
        if client.status is not ClientStatus.ACTIVE:
            continue
        days = ctx.daily.get(client_id, {})
        today = days.get(ctx.today)
        if today is None or today.cost_usd < COST_SPIKE_MIN_USD:
            continue
        previous = [
            days.get(ctx.today - timedelta(days=n), DayStats()).cost_usd for n in range(1, 15)
        ]
        median = Decimal(str(statistics.median(previous)))
        if today.cost_usd > factor * median:
            out.append(
                Finding(
                    cfg.code,
                    cfg.severity,
                    client_id,
                    None,
                    {"cost_usd": str(today.cost_usd), "median_14d_usd": str(median)},
                )
            )
    return out


def instance_warning(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    out: list[Finding] = []
    for i in _live_instances(ctx):
        raw: list[Any] = (i.last_heartbeat or {}).get("warnings") or []
        present = sorted(w for w in raw if isinstance(w, str) and w in INSTANCE_WARNING_CODES)
        if present:
            out.append(_finding(cfg, i, i.client_id, {"instance": i.name, "warnings": present}))
    return out


def instance_outdated(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    if not ctx.latest_version or ctx.latest_published_at is None:
        return []  # sin fecha de publicación no se sabe desde cuándo está desactualizada
    if ctx.now - ctx.latest_published_at <= timedelta(days=cfg.threshold or 30):
        return []
    return [
        _finding(
            cfg,
            i,
            i.client_id,
            {"instance": i.name, "version": i.version, "latest": ctx.latest_version},
        )
        for i in _live_instances(ctx)
        if is_outdated(i.version, ctx.latest_version)
    ]


def no_usage(ctx: EvalContext, cfg: RuleConfig) -> list[Finding]:
    window = int(cfg.threshold or 14)
    online_by_client: set[UUID] = {
        i.client_id
        for i in _live_instances(ctx)
        if i.status is InstanceStatus.ACTIVE and is_online(i.last_seen_at, ctx.now)
    }
    out: list[Finding] = []
    for client_id in online_by_client:
        days = ctx.daily.get(client_id, {})
        turns = sum(
            days.get(ctx.today - timedelta(days=n), DayStats()).turns for n in range(window)
        )
        if turns == 0:
            out.append(Finding(cfg.code, cfg.severity, client_id, None, {"days": window}))
    return out


EVALUATORS = {
    "instance_offline": instance_offline,
    "instance_fingerprint_mismatch": instance_fingerprint_mismatch,
    "sync_stalled": sync_stalled,
    "contract_rejected": contract_rejected,
    "clock_skew": clock_skew,
    "error_rate_spike": error_rate_spike,
    "cost_spike": cost_spike,
    "instance_warning": instance_warning,
    "instance_outdated": instance_outdated,
    "no_usage": no_usage,
}
