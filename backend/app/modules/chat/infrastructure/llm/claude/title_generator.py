"""Auto-título con Claude (modelo barato dedicado, Haiku por default)."""

import logging

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from app.infrastructure.claude_cli import resolve_cli_path
from app.infrastructure.claude_env import build_claude_env
from app.infrastructure.config import Settings
from app.modules.chat.domain.interfaces import ActiveProvider, TitleGenerator
from app.modules.chat.infrastructure.llm.claude.mcp_adapter import BUILTIN_TOOLS
from app.modules.chat.infrastructure.llm.title_prompt import (
    TITLE_SYSTEM_PROMPT,
    build_title_prompt,
    clean_title,
)

log = logging.getLogger(__name__)


class ClaudeTitleGenerator(TitleGenerator):
    def __init__(self, settings: Settings, provider: ActiveProvider) -> None:
        self._settings = settings
        self._provider = provider

    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        options = ClaudeAgentOptions(
            model=self._provider.title_model,
            system_prompt=TITLE_SYSTEM_PROMPT,
            # Titular no necesita ninguna herramienta, y el texto que se le
            # manda es del usuario: sin `tools=[]` el CLI traería Bash, Read
            # y compañía, aprobadas por `bypassPermissions`.
            tools=[],
            allowed_tools=[],
            disallowed_tools=list(BUILTIN_TOOLS),
            permission_mode="bypassPermissions",
            max_turns=1,
            cli_path=resolve_cli_path(),
            env=build_claude_env(
                credential_kind=self._provider.credential_kind,
                credential=self._provider.credential,
                git_bash_path=self._settings.claude_code_git_bash_path,
            ),
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
