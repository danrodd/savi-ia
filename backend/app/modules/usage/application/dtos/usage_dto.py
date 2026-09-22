from dataclasses import dataclass
from datetime import datetime

from app.modules.usage.domain.value_objects import (
    ConversationStats,
    DailyProviderUsage,
    DailyUsage,
    ProviderUsage,
    UsageTotals,
    UserStats,
    UserUsage,
)


@dataclass(frozen=True)
class UserUsageReportDTO:
    """Reporte de consumo de un usuario: total + serie diaria + proveedor."""

    user_id: int
    period_start: datetime
    period_end: datetime
    totals: UsageTotals
    daily: list[DailyUsage]
    per_provider: list[ProviderUsage]
    daily_by_provider: list[DailyProviderUsage]


@dataclass(frozen=True)
class SystemUsageReportDTO:
    """Reporte de consumo del sistema: total + ranking por usuario + serie."""

    period_start: datetime
    period_end: datetime
    totals: UsageTotals
    per_user: list[UserUsage]
    daily: list[DailyUsage]
    per_provider: list[ProviderUsage]
    daily_by_provider: list[DailyProviderUsage]


@dataclass(frozen=True)
class UsageKpisDTO:
    """KPIs de consumo para análisis de tarifa.

    Combina agregados de la BD (totales, stats por conversación/usuario)
    con derivaciones de negocio (costo por turno, proyección mensual,
    ratio de caché).
    """

    period_start: datetime
    period_end: datetime
    period_days: int
    total_cost_usd: float
    total_tokens: int
    turns_count: int
    avg_cost_per_turn_usd: float
    avg_tokens_per_turn: float
    conversations: ConversationStats
    users: UserStats
    avg_cost_per_day_usd: float
    projected_monthly_cost_usd: float
    # cache_read / (input + cache_read + cache_creation). El cache_read
    # cuesta ~10% del input, así que un ratio alto baja el costo unitario.
    cache_read_ratio: float
