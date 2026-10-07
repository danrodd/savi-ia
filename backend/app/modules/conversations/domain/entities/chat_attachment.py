"""Imagen adjunta a un mensaje del chat.

Solo metadata: los bytes viven en otra tabla y se piden aparte, para que
listar mensajes nunca los cargue.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ChatAttachment:
    user_id: int
    # Base de IDENTIDAD del dueño: el `idUsuario` se repite entre clientes,
    # así que sin ella dos usuarios distintos compartirían adjuntos.
    owner_erp_database_id: UUID
    mime: str
    filename: str
    size_bytes: int
    width: int
    height: int
    id: UUID = field(default_factory=uuid4)
    # `None` mientras no se envió el mensaje: subida y envío son dos pasos.
    message_id: UUID | None = None
    created_at: datetime = field(default_factory=_utc_now)
