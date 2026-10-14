from pydantic import BaseModel, Field

from app.modules.feedback.domain.value_objects import (
    COMMENT_MAX_LENGTH,
    FeedbackRating,
    FeedbackReason,
)


class SetFeedbackRequest(BaseModel):
    rating: FeedbackRating
    # Solo con `down`; con `up` el servidor responde 422.
    reason: FeedbackReason | None = None
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)
