from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """Agregado de consumo de un conjunto de turnos.

    El costo se mantiene SIEMPRE en USD — es lo que reporta el SDK de
    Claude (`ResultMessage.total_cost_usd`). La conversión a COP es
    responsabilidad de la vista, no de este dominio.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    # Cantidad de turnos del asistente que contribuyeron al agregado.
    message_count: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )


@dataclass(frozen=True, slots=True)
class DailyUsage:
    """Consumo agregado de un día (en la zona horaria de reporte)."""

    day: date
    totals: UsageTotals


@dataclass(frozen=True, slots=True)
class UserUsage:
    """Consumo agregado de un usuario en el período consultado.

    La identidad es el par `(erp_database_id, user_id)`: el `idUsuario`
    del ERP se repite entre bases de clientes, y agrupar solo por el
    entero fusionaria en una sola fila a personas distintas.

    Ambos pueden ser `None`: corresponde a conversaciones legadas
    anteriores a auth o al multi-BD, que igual costaron tokens.
    """

    user_id: int | None
    totals: UsageTotals
    erp_database_id: UUID | None = None
