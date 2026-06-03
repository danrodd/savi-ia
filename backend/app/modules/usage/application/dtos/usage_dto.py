from dataclasses import dataclass
from datetime import datetime

from app.modules.usage.domain.value_objects import (
    DailyUsage,
    UsageTotals,
    UserUsage,
)


@dataclass(frozen=True)
class UserUsageReportDTO:
    """Reporte de consumo de un usuario: total + serie diaria."""

    user_id: int
    period_start: datetime
    period_end: datetime
    totals: UsageTotals
    daily: list[DailyUsage]


@dataclass(frozen=True)
class SystemUsageReportDTO:
    """Reporte de consumo del sistema: total + ranking por usuario + serie."""

    period_start: datetime
    period_end: datetime
    totals: UsageTotals
    per_user: list[UserUsage]
    daily: list[DailyUsage]
