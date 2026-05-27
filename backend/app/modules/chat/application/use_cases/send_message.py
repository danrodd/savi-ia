import contextlib
from collections.abc import AsyncIterator
from uuid import UUID

from app.modules.chat.domain.entities import ChatEvent, ChatEventType
from app.modules.chat.domain.interfaces import LLMRunner
from app.modules.conversations.domain.entities import Message, MessageRole
from app.modules.conversations.domain.exceptions import ConversationNotFoundError
from app.modules.conversations.domain.interfaces import ConversationRepository

_HISTORY_TURNS = 20
_HISTORY_CHAR_LIMIT = 1500
_NEW_QUERY_MARKER = "=== Nueva consulta del usuario (responde esta) ==="


def _format_history_block(messages: list[Message]) -> str:
    if not messages:
        return ""
    recent = messages[-_HISTORY_TURNS:]
    lines = ["=== Historial de esta conversación ==="]
    for m in recent:
        who = "Usuario" if m.role == MessageRole.USER else "SAVI"
        body = m.content.strip()
        if len(body) > _HISTORY_CHAR_LIMIT:
            body = body[:_HISTORY_CHAR_LIMIT] + " …"
        lines.append(f"{who}: {body}")
    lines.append(_NEW_QUERY_MARKER)
    return "\n\n".join(lines) + "\n\n"


class SendMessageUseCase:
    def __init__(
        self,
        repository: ConversationRepository,
        runner: LLMRunner,
    ) -> None:
        self._repository = repository
        self._runner = runner

    async def execute(
        self,
        conversation_id: UUID,
        user_text: str,
    ) -> AsyncIterator[ChatEvent]:
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.is_deleted:
            raise ConversationNotFoundError(conversation_id)

        history = await self._repository.list_messages(conversation_id)

        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_text,
        )
        await self._repository.add_message(user_message)

        prompt = _format_history_block(history) + user_text.strip()

        accumulated: list[str] = []
        try:
            async for event in self._runner.stream_turn(prompt):
                if event.type == ChatEventType.TEXT_DELTA:
                    accumulated.append(event.text)  # type: ignore[union-attr]
                yield event
        finally:
            if accumulated:
                assistant_message = Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content="".join(accumulated),
                )
                with contextlib.suppress(Exception):
                    await self._repository.add_message(assistant_message)
