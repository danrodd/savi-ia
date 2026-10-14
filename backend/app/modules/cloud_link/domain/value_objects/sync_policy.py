from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

# Tope duro del contrato `sync/v1` (eventos por lote) y piso del reintento
# cuando Cloud responde 413.
CONTRACT_MAX_BATCH_EVENTS = 500
MIN_BATCH_EVENTS = 50


class SyncStream(StrEnum):
    TURN = "turn"
    CONVERSATION = "conversation"
    SESSION = "session"
    FREE_QUERY = "free_query"
    DATABASE = "database"

    @property
    def schema(self) -> str:
        """Valor del campo `schema` de cada evento del stream."""
        return f"{self.value}/1"


INCREMENTAL_STREAMS: tuple[SyncStream, ...] = (
    SyncStream.TURN,
    SyncStream.CONVERSATION,
    SyncStream.SESSION,
    SyncStream.FREE_QUERY,
)


# Valores de `identity_mode` que esta instalación entiende. Uno desconocido se trata como
# `pseudonym`: ante la duda, lo más privado.
IDENTITY_PSEUDONYM = "pseudonym"
IDENTITY_NAMED = "named"


def _no_amounts() -> dict[str, Decimal]:
    return {}


@dataclass(frozen=True, slots=True)
class AiLimits:
    """Proveedores permitidos y topes mensuales de IA que fija Cloud (USD).

    La instancia mide con su propio consumo y bloquea antes de abrir el chat.
    """

    # `None` = todos los proveedores.
    allowed_providers: frozenset[str] | None = None
    # Tope mensual por persona. `None` = sin tope.
    user_monthly_usd: Decimal | None = None
    # Tope mensual de toda la instalación, por proveedor.
    provider_monthly_usd: dict[str, Decimal] = field(default_factory=_no_amounts)
    # Tope propio de una persona (`user_ref`) en lugar del general. `0` la deja sin IA.
    user_overrides: dict[str, Decimal] = field(default_factory=_no_amounts)

    @property
    def is_unlimited(self) -> bool:
        return (
            self.allowed_providers is None
            and self.user_monthly_usd is None
            and not self.provider_monthly_usd
            and not self.user_overrides
        )

    def user_cap(self, user_ref: str) -> Decimal | None:
        return self.user_overrides.get(user_ref, self.user_monthly_usd)


@dataclass(frozen=True, slots=True)
class SyncPolicy:
    """Política que Cloud informa en el enroll y en cada heartbeat."""

    heartbeat_seconds: int = 300
    ingest_seconds: int = 300
    max_batch_events: int = CONTRACT_MAX_BATCH_EVENTS
    sync_enabled: bool = True
    # Esta instalación queda solo con el chat: SEO Group la administra desde Cloud.
    config_locked: bool = False
    # La instalación puede ofrecer el CLI de Claude con la cuenta de la persona
    # (`local_session`). Apagado por defecto: lo habilita SEO Group por cliente.
    allow_local_cli: bool = False
    # `named`: las sesiones llevan el código de usuario (organización interna). Por defecto,
    # solo seudónimos.
    identity_mode: str = "pseudonym"
    # Proveedores y topes de IA. `None` = sin límites.
    ai: AiLimits | None = None
