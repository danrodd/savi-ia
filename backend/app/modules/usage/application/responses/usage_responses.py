from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.usage.application.dtos import (
    SystemUsageReportDTO,
    UsageKpisDTO,
    UserUsageReportDTO,
)
from app.modules.usage.domain.value_objects import (
    ConversationStats,
    ConversationUsage,
    DailyProviderUsage,
    DailyUsage,
    ProviderUsage,
    UsageTotals,
    UserStats,
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
    # Turnos sin tarifa cargada para su modelo: su costo NO está incluido
    # arriba. Si es > 0, el total mostrado es menor al real y la vista tiene
    # que decirlo en lugar de dar un número que parece completo.
    untariffed_count: int = 0

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
            untariffed_count=t.untariffed_count,
        )


class DailyUsageResponse(BaseModel):
    day: date
    totals: UsageTotalsResponse

    @classmethod
    def from_vo(cls, d: DailyUsage) -> "DailyUsageResponse":
        return cls(day=d.day, totals=UsageTotalsResponse.from_vo(d.totals))


class ProviderUsageResponse(BaseModel):
    provider: str | None
    model: str | None
    totals: UsageTotalsResponse

    @classmethod
    def from_vo(cls, p: ProviderUsage) -> "ProviderUsageResponse":
        return cls(provider=p.provider, model=p.model, totals=UsageTotalsResponse.from_vo(p.totals))


class DailyProviderUsageResponse(BaseModel):
    day: date
    provider: str | None
    totals: UsageTotalsResponse

    @classmethod
    def from_vo(cls, d: DailyProviderUsage) -> "DailyProviderUsageResponse":
        return cls(day=d.day, provider=d.provider, totals=UsageTotalsResponse.from_vo(d.totals))


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
    per_provider: list[ProviderUsageResponse]
    daily_by_provider: list[DailyProviderUsageResponse]
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
            per_provider=[ProviderUsageResponse.from_vo(p) for p in dto.per_provider],
            daily_by_provider=[
                DailyProviderUsageResponse.from_vo(d) for d in dto.daily_by_provider
            ],
            usd_to_cop_rate=usd_to_cop_rate,
        )


class SystemUsageReportResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    totals: UsageTotalsResponse
    per_user: list[UserUsageResponse]
    daily: list[DailyUsageResponse]
    per_provider: list[ProviderUsageResponse]
    daily_by_provider: list[DailyProviderUsageResponse]
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
            per_provider=[ProviderUsageResponse.from_vo(p) for p in dto.per_provider],
            daily_by_provider=[
                DailyProviderUsageResponse.from_vo(d) for d in dto.daily_by_provider
            ],
            usd_to_cop_rate=usd_to_cop_rate,
        )


class ConversationStatsResponse(BaseModel):
    count: int
    avg_cost_usd: float
    p50_cost_usd: float
    p90_cost_usd: float
    p95_cost_usd: float
    max_cost_usd: float
    avg_tokens: float
    avg_turns: float

    @classmethod
    def from_vo(cls, s: ConversationStats) -> "ConversationStatsResponse":
        return cls(
            count=s.count,
            avg_cost_usd=s.avg_cost_usd,
            p50_cost_usd=s.p50_cost_usd,
            p90_cost_usd=s.p90_cost_usd,
            p95_cost_usd=s.p95_cost_usd,
            max_cost_usd=s.max_cost_usd,
            avg_tokens=s.avg_tokens,
            avg_turns=s.avg_turns,
        )


class UserStatsResponse(BaseModel):
    active_count: int
    avg_cost_usd: float
    avg_conversations: float

    @classmethod
    def from_vo(cls, s: UserStats) -> "UserStatsResponse":
        return cls(
            active_count=s.active_count,
            avg_cost_usd=s.avg_cost_usd,
            avg_conversations=s.avg_conversations,
        )


class UsageKpisResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    period_days: int
    total_cost_usd: float
    total_tokens: int
    turns_count: int
    avg_cost_per_turn_usd: float
    avg_tokens_per_turn: float
    conversations: ConversationStatsResponse
    users: UserStatsResponse
    avg_cost_per_day_usd: float
    projected_monthly_cost_usd: float
    cache_read_ratio: float
    usd_to_cop_rate: float

    @classmethod
    def from_dto(
        cls, dto: UsageKpisDTO, *, usd_to_cop_rate: float
    ) -> "UsageKpisResponse":
        return cls(
            period_start=dto.period_start,
            period_end=dto.period_end,
            period_days=dto.period_days,
            total_cost_usd=dto.total_cost_usd,
            total_tokens=dto.total_tokens,
            turns_count=dto.turns_count,
            avg_cost_per_turn_usd=dto.avg_cost_per_turn_usd,
            avg_tokens_per_turn=dto.avg_tokens_per_turn,
            conversations=ConversationStatsResponse.from_vo(dto.conversations),
            users=UserStatsResponse.from_vo(dto.users),
            avg_cost_per_day_usd=dto.avg_cost_per_day_usd,
            projected_monthly_cost_usd=dto.projected_monthly_cost_usd,
            cache_read_ratio=dto.cache_read_ratio,
            usd_to_cop_rate=usd_to_cop_rate,
        )


class ConversationUsageResponse(BaseModel):
    conversation_id: UUID
    user_id: int | None
    title: str
    turns: int
    total_tokens: int
    cost_usd: float
    last_activity: datetime

    @classmethod
    def from_vo(cls, c: ConversationUsage) -> "ConversationUsageResponse":
        return cls(
            conversation_id=c.conversation_id,
            user_id=c.user_id,
            title=c.title,
            turns=c.turns,
            total_tokens=c.total_tokens,
            cost_usd=c.cost_usd,
            last_activity=c.last_activity,
        )
