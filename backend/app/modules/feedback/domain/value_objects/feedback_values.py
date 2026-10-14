"""Valores del feedback por respuesta: calificación, motivo y filtros del panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

# Tope del comentario libre. Lo valida la request y lo repite la BD (columna).
COMMENT_MAX_LENGTH = 1000

# Recortes del panel de administración: el detalle completo vive en la
# conversación; acá solo hace falta contexto para entender la calificación.
QUESTION_MAX_CHARS = 2000
ANSWER_MAX_CHARS = 4000


class FeedbackRating(StrEnum):
    UP = "up"
    DOWN = "down"


class FeedbackReason(StrEnum):
    """Por qué una respuesta no sirvió. Solo aplica a `FeedbackRating.DOWN`."""

    WRONG_DATA = "dato_incorrecto"
    NOT_UNDERSTOOD = "no_entendio"
    INCOMPLETE = "incompleta"
    TOO_SLOW = "muy_lenta"
    OTHER = "otra"


@dataclass(frozen=True, slots=True)
class FeedbackFilters:
    """Filtros del panel y del export. `None` = sin filtro en esa dimensión.

    `start`/`end` son instantes UTC con el rango `[start, end)` ya resuelto por
    la capa HTTP (corte de día en la zona de reporte).
    """

    rating: FeedbackRating | None = None
    reason: FeedbackReason | None = None
    start: datetime | None = None
    end: datetime | None = None
    provider: str | None = None
    model: str | None = None
    # Texto parcial del código de usuario (sin distinguir mayúsculas).
    user: str | None = None
    # Texto parcial dentro del comentario.
    text: str | None = None


def _no_tools() -> tuple[str, ...]:
    return ()


@dataclass(frozen=True, slots=True)
class FeedbackReportItem:
    """Una calificación con el contexto que el administrador necesita.

    Nunca lleva entradas de herramientas ni SQL: solo el NOMBRE de cada una.
    """

    id: str
    rating: FeedbackRating
    reason: FeedbackReason | None
    comment: str | None
    created_at: datetime
    updated_at: datetime
    user_id: int
    user_login: str | None
    user_name: str | None
    conversation_id: str
    message_id: str
    question: str | None
    answer: str
    provider: str | None
    model: str | None
    cost_usd: float | None
    tools: tuple[str, ...] = field(default_factory=_no_tools)
    database_code: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackPage:
    items: list[FeedbackReportItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class DailyFeedback:
    day: str  # AAAA-MM-DD en la zona de reporte
    up: int
    down: int


@dataclass(frozen=True, slots=True)
class ReasonCount:
    reason: FeedbackReason
    count: int


@dataclass(frozen=True, slots=True)
class ModelFeedback:
    provider: str | None
    model: str | None
    up: int
    down: int


@dataclass(frozen=True, slots=True)
class FeedbackSummary:
    total: int
    up: int
    down: int
    # `None` si no hay calificaciones (evita un 0 % engañoso).
    positive_pct: float | None
    daily: list[DailyFeedback]
    top_reasons: list[ReasonCount]
    by_model: list[ModelFeedback]
