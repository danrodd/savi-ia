from app.modules.usage.application.dtos import UsageKpisDTO
from app.modules.usage.domain.interfaces import UsageRepository
from app.modules.usage.domain.value_objects import UsagePeriod

# Días "comerciales" usados para anualizar/proyectar el costo mensual.
_DAYS_PER_MONTH = 30


class GetUsageKpisUseCase:
    """Calcula los KPIs de consumo para definir tarifa.

    El repositorio aporta los agregados crudos (totales + stats por
    conversación/usuario con percentiles); este use case deriva las
    métricas de negocio: costo por turno, costo por día, proyección
    mensual y ratio de caché.
    """

    def __init__(self, repository: UsageRepository):
        self._repository = repository

    async def execute(self, period: UsagePeriod) -> UsageKpisDTO:
        totals = await self._repository.system_totals(period)
        conversations = await self._repository.conversation_stats(period)
        users = await self._repository.user_stats(period)

        total_cost = float(totals.cost_usd)
        turns = totals.message_count
        period_days = max(1, (period.end - period.start).days)

        avg_cost_per_turn = total_cost / turns if turns else 0.0
        avg_tokens_per_turn = totals.total_tokens / turns if turns else 0.0
        avg_cost_per_day = total_cost / period_days
        projected_monthly = avg_cost_per_day * _DAYS_PER_MONTH

        # "Input total" = todo lo que entra al modelo: input fresco + lo
        # que se leyó de caché + lo que se escribió en caché.
        input_like = (
            totals.input_tokens
            + totals.cache_read_input_tokens
            + totals.cache_creation_input_tokens
        )
        cache_read_ratio = (
            totals.cache_read_input_tokens / input_like if input_like else 0.0
        )

        return UsageKpisDTO(
            period_start=period.start,
            period_end=period.end,
            period_days=period_days,
            total_cost_usd=total_cost,
            total_tokens=totals.total_tokens,
            turns_count=turns,
            avg_cost_per_turn_usd=avg_cost_per_turn,
            avg_tokens_per_turn=avg_tokens_per_turn,
            conversations=conversations,
            users=users,
            avg_cost_per_day_usd=avg_cost_per_day,
            projected_monthly_cost_usd=projected_monthly,
            cache_read_ratio=cache_read_ratio,
        )
