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
    # Turnos SIN costo calculado: el proveedor no tenía tarifa cargada para
    # ese modelo, así que `cost_usd` quedó NULL. Se cuentan aparte porque
    # sumarlos como cero hace que la pantalla muestre un costo menor al real
    # sin decir que le falta información. Medido: las respuestas de Gemini
    # figuraban en USD 0,00 por no tener tarifa.
    untariffed_count: int = 0

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
class ProviderUsage:
    """Consumo agregado de un (proveedor, modelo) en el período consultado.

    Siempre agrupado por modelo: el desglose por proveedor solo (sin
    modelo) lo arma la vista sumando las filas que comparten `provider`.
    """

    provider: str | None
    model: str | None
    totals: UsageTotals


@dataclass(frozen=True, slots=True)
class DatabaseUsage:
    """Consumo agregado por base del ERP CONSULTADA en el período.

    Es la base de la conversación, no la de login del dueño: un usuario de
    soporte atiende a varios clientes desde una sola sesión, y lo que se
    quiere saber es cuánto costó cada cliente. `None` agrupa conversaciones
    legadas anteriores al multi-BD.
    """

    erp_database_id: UUID | None
    totals: UsageTotals


@dataclass(frozen=True, slots=True)
class DailyProviderUsage:
    """Consumo agregado de un día, desglosado por proveedor (no por modelo:
    alimenta la barra apilada, donde una serie por modelo sería ilegible)."""

    day: date
    provider: str | None
    totals: UsageTotals


@dataclass(frozen=True, slots=True)
class UserUsage:
    """Consumo agregado de un usuario en el período consultado.

    La identidad es el par `(erp_database_id, user_id)`: el `idUsuario`
    del ERP se repite entre bases de clientes, y agrupar solo por el
    entero fusionaria en una sola fila a personas distintas.

    `erp_database_id` es la base con la que el usuario INICIÓ SESIÓN
    (`owner_erp_database_id` de la conversación), no la consultada: el
    `idUsuario` solo significa algo en la base donde se autenticó. Con la
    consultada, los chats de un usuario de soporte contra otro cliente se
    le atribuían a quien tuviera ese mismo id en ese cliente.

    Ambos pueden ser `None`: corresponde a conversaciones legadas
    anteriores a auth o al multi-BD, que igual costaron tokens.
    """

    user_id: int | None
    totals: UsageTotals
    erp_database_id: UUID | None = None
