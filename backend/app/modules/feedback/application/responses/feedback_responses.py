from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.conversations.application.responses import MessageFeedbackResponse
from app.modules.feedback.domain.entities import MessageFeedback
from app.modules.feedback.domain.value_objects import (
    DailyFeedback,
    FeedbackPage,
    FeedbackReportItem,
    FeedbackSummary,
    ModelFeedback,
    ReasonCount,
)


def to_message_feedback(feedback: MessageFeedback) -> MessageFeedbackResponse:
    return MessageFeedbackResponse(
        rating=feedback.rating.value,
        reason=feedback.reason.value if feedback.reason else None,
        comment=feedback.comment,
    )


class FeedbackResponse(MessageFeedbackResponse):
    """Resultado del `PUT`: la calificación guardada."""

    message_id: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, feedback: MessageFeedback) -> "FeedbackResponse":
        return cls(
            rating=feedback.rating.value,
            reason=feedback.reason.value if feedback.reason else None,
            comment=feedback.comment,
            message_id=feedback.message_id,
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
        )


def _no_tools() -> list[str]:
    return []


class AdminFeedbackItemResponse(BaseModel):
    id: UUID
    rating: str
    reason: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime
    user_id: int
    user_login: str | None
    user_name: str | None
    conversation_id: UUID
    message_id: UUID
    question: str | None
    answer: str
    provider: str | None
    model: str | None
    cost_usd: float | None
    tools: list[str] = Field(default_factory=_no_tools)
    database_code: str | None

    @classmethod
    def from_vo(cls, item: FeedbackReportItem) -> "AdminFeedbackItemResponse":
        return cls(
            id=UUID(item.id),
            rating=item.rating.value,
            reason=item.reason.value if item.reason else None,
            comment=item.comment,
            created_at=item.created_at,
            updated_at=item.updated_at,
            user_id=item.user_id,
            user_login=item.user_login,
            user_name=item.user_name,
            conversation_id=UUID(item.conversation_id),
            message_id=UUID(item.message_id),
            question=item.question,
            answer=item.answer,
            provider=item.provider,
            model=item.model,
            cost_usd=item.cost_usd,
            tools=list(item.tools),
            database_code=item.database_code,
        )


class AdminFeedbackPageResponse(BaseModel):
    items: list[AdminFeedbackItemResponse]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_vo(cls, page: FeedbackPage) -> "AdminFeedbackPageResponse":
        return cls(
            items=[AdminFeedbackItemResponse.from_vo(i) for i in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )


class DailyFeedbackResponse(BaseModel):
    day: str
    up: int
    down: int

    @classmethod
    def from_vo(cls, vo: DailyFeedback) -> "DailyFeedbackResponse":
        return cls(day=vo.day, up=vo.up, down=vo.down)


class ReasonCountResponse(BaseModel):
    reason: str
    count: int

    @classmethod
    def from_vo(cls, vo: ReasonCount) -> "ReasonCountResponse":
        return cls(reason=vo.reason.value, count=vo.count)


class ModelFeedbackResponse(BaseModel):
    provider: str | None
    model: str | None
    up: int
    down: int

    @classmethod
    def from_vo(cls, vo: ModelFeedback) -> "ModelFeedbackResponse":
        return cls(provider=vo.provider, model=vo.model, up=vo.up, down=vo.down)


class FeedbackSummaryResponse(BaseModel):
    total: int
    up: int
    down: int
    positive_pct: float | None
    daily: list[DailyFeedbackResponse]
    top_reasons: list[ReasonCountResponse]
    by_model: list[ModelFeedbackResponse]

    @classmethod
    def from_vo(cls, vo: FeedbackSummary) -> "FeedbackSummaryResponse":
        return cls(
            total=vo.total,
            up=vo.up,
            down=vo.down,
            positive_pct=vo.positive_pct,
            daily=[DailyFeedbackResponse.from_vo(d) for d in vo.daily],
            top_reasons=[ReasonCountResponse.from_vo(r) for r in vo.top_reasons],
            by_model=[ModelFeedbackResponse.from_vo(m) for m in vo.by_model],
        )
