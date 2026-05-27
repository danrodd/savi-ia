from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ChatEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    DONE = "done"
    ERROR = "error"


@dataclass(slots=True)
class TextDeltaEvent:
    text: str
    type: ChatEventType = ChatEventType.TEXT_DELTA


@dataclass(slots=True)
class ThinkingDeltaEvent:
    text: str
    type: ChatEventType = ChatEventType.THINKING_DELTA


@dataclass(slots=True)
class ToolUseEvent:
    id: str
    name: str
    input: dict[str, Any]
    type: ChatEventType = ChatEventType.TOOL_USE


@dataclass(slots=True)
class ToolResultEvent:
    tool_use_id: str
    is_error: bool
    type: ChatEventType = ChatEventType.TOOL_RESULT


@dataclass(slots=True)
class DoneEvent:
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None
    finish_reason: str = "complete"
    type: ChatEventType = ChatEventType.DONE


@dataclass(slots=True)
class ErrorEvent:
    message: str
    type: ChatEventType = ChatEventType.ERROR


ChatEvent = (
    TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolUseEvent
    | ToolResultEvent
    | DoneEvent
    | ErrorEvent
)
