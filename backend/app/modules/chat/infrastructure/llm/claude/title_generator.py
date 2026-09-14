"""Auto-título con Claude (modelo barato dedicado, Haiku por default)."""

import logging

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from app.infrastructure.config import Settings
from app.modules.chat.domain.interfaces import TitleGenerator
from app.modules.chat.infrastructure.llm.claude.sdk_env import apply_sdk_env
from app.modules.chat.infrastructure.llm.title_prompt import (
    TITLE_SYSTEM_PROMPT,
    build_title_prompt,
    clean_title,
)

log = logging.getLogger(__name__)


class ClaudeTitleGenerator(TitleGenerator):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        apply_sdk_env(self._settings)
        options = ClaudeAgentOptions(
            model=self._settings.claude_title_model,
            system_prompt=TITLE_SYSTEM_PROMPT,
            allowed_tools=[],
            permission_mode="bypassPermissions",
            max_turns=1,
        )
        prompt = build_title_prompt(user_msg, assistant_msg)
        parts: list[str] = []
        try:
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    parts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
        except Exception:
            log.exception("title_generation_failed")
            return None
        return clean_title("".join(parts))
