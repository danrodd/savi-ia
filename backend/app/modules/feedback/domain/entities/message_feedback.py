from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.feedback.domain.value_objects import FeedbackRating, FeedbackReason


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class MessageFeedback:
    """Calificación de UNA respuesta del asistente por UN usuario.

    La identidad del autor es el par `(user_id, owner_erp_database_id)`: el
    `idUsuario` del ERP se repite entre clientes.
    """

    message_id: UUID
    user_id: int
    owner_erp_database_id: UUID
    rating: FeedbackRating
    reason: FeedbackReason | None = None
    comment: str | None = None
    # Quién calificó, tal como se autenticó. El `idUsuario` solo no le dice
    # nada al administrador: se guarda el código y el nombre del momento.
    user_login: str | None = None
    user_name: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
