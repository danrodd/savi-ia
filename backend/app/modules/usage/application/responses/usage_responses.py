from datetime import date, datetime

from pydantic import BaseModel

from app.modules.usage.application.dtos import (
    SystemUsageReportDTO,
    UserUsageReportDTO,
)
from app.modules.usage.domain.value_objects import (
    DailyUsage,
    UsageTotals,
    UserUsage,
)


class UsageTotalsResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    total_tokens: int
    message_count: int
    # Costo en USD (dato fuente). El frontend lo multiplica por
    # `usd_to_cop_rate` para mostrarlo en pesos.
    cost_usd: float

    @classmethod
    def from_vo(cls, t: UsageTotals) -> "UsageTotalsResponse":
        return cls(
            input_tokens=t.input_tokens,
            output_tokens=t.output_tokens,
            cache_read_input_tokens=t.cache_read_input_tokens,
            cache_creation_input_tokens=t.cache_creation_input_tokens,
            total_tokens=t.total_tokens,
            message_count=t.message_count,
            cost_usd=float(t.cost_usd),
        )


class DailyUsageResponse(BaseModel):
    day: date
    totals: UsageTotalsResponse

    @classmethod
    def from_vo(cls, d: DailyUsage) -> "DailyUsageResponse":
        return cls(day=d.day, totals=UsageTotalsResponse.from_vo(d.totals))


class UserUsageResponse(BaseModel):
    user_id: int | None
    totals: UsageTotalsResponse

    @classmethod
    def from_vo(cls, u: UserUsage) -> "UserUsageResponse":
        return cls(user_id=u.user_id, totals=UsageTotalsResponse.from_vo(u.totals))


class UserUsageReportResponse(BaseModel):
    user_id: int
    period_start: datetime
    period_end: datetime
    totals: UsageTotalsResponse
    daily: list[DailyUsageResponse]
    # Tasa de cambio para que la vista convierta USD → COP. Se expone acá
    # para que haya una única fuente de verdad (configurada en backend).
    usd_to_cop_rate: float

    @classmethod
    def from_dto(
        cls, dto: UserUsageReportDTO, *, usd_to_cop_rate: float
    ) -> "UserUsageReportResponse":
        return cls(
            user_id=dto.user_id,
            period_start=dto.period_start,
            period_end=dto.period_end,
            totals=UsageTotalsResponse.from_vo(dto.totals),
            daily=[DailyUsageResponse.from_vo(d) for d in dto.daily],
            usd_to_cop_rate=usd_to_cop_rate,
        )


class SystemUsageReportResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    totals: UsageTotalsResponse
    per_user: list[UserUsageResponse]
    daily: list[DailyUsageResponse]
    usd_to_cop_rate: float

    @classmethod
    def from_dto(
        cls, dto: SystemUsageReportDTO, *, usd_to_cop_rate: float
    ) -> "SystemUsageReportResponse":
        return cls(
            period_start=dto.period_start,
            period_end=dto.period_end,
            totals=UsageTotalsResponse.from_vo(dto.totals),
            per_user=[UserUsageResponse.from_vo(u) for u in dto.per_user],
            daily=[DailyUsageResponse.from_vo(d) for d in dto.daily],
            usd_to_cop_rate=usd_to_cop_rate,
        )
