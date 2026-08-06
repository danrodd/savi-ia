"""Runner del agente SAVI sobre el Claude Agent SDK.

Cada turno construye un nuevo MCP server in-process (para poder, más
adelante, atar las tools al usuario actual por clausura) y emite eventos
tipados listos para serializar como SSE.

El SDK levanta el binario `claude` como subprocess; en Windows necesita
`CLAUDE_CODE_GIT_BASH_PATH` apuntando a `bash.exe` (lo propagamos desde
`Settings`).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from uuid import UUID

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from app.infrastructure.config import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import LLMRunner
from app.modules.chat.infrastructure.llm.mcp.server import (
    ALLOWED_TOOLS,
    MCP_SERVER_NAME,
    build_savi_mcp_server,
)
from app.modules.chat.infrastructure.llm.system_prompt import SYSTEM_PROMPT

log = logging.getLogger(__name__)

_TRUNCATION_NOTICE = (
    "\n\n_(Respuesta truncada por límite de tamaño. Si necesitas más "
    "detalle, pídeme una sección específica.)_"
)


def _apply_sdk_env(settings: Settings) -> None:
    if settings.claude_code_oauth_token:
        os.environ.setdefault("CLAUDE_CODE_OAUTH_TOKEN", settings.claude_code_oauth_token)
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.claude_code_git_bash_path:
        os.environ.setdefault(
            "CLAUDE_CODE_GIT_BASH_PATH",
            settings.claude_code_git_bash_path,
        )


def _build_options(
    settings: Settings,
    *,
    conversation_id: UUID | None,
    allowed_modules: frozenset[ModuleCode] | None,
) -> ClaudeAgentOptions:
    mcp_server = build_savi_mcp_server(
        conversation_id=conversation_id, allowed_modules=allowed_modules
    )
    return ClaudeAgentOptions(
        model=settings.claude_model,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={MCP_SERVER_NAME: mcp_server},
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=settings.max_agent_turns,
    )


async def _open_query_stream(prompt: str, options: ClaudeAgentOptions):
    """Wrap `query()` with a single retry on initialize-timeout errors.

    El CLI empaquetado tarda en arrancar bajo carga; el SDK lanza
    `Control request timeout: initialize`. Un retry corto lo resuelve
    en la mayoría de casos.
    """
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            async for msg in query(prompt=prompt, options=options):
                yield msg
            return
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if "Control request timeout" in str(e) and attempt == 0:
                log.warning("agent_initialize_timeout_retrying error=%s", e)
                await asyncio.sleep(1.5)
                continue
            raise
    if last_exc is not None:
        raise last_exc


class ClaudeAgentRunner(LLMRunner):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        _apply_sdk_env(settings)

    async def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
        allowed_modules: frozenset[ModuleCode] | None = None,
    ) -> AsyncIterator[ChatEvent]:
        options = _build_options(
            self._settings,
            conversation_id=conversation_id,
            allowed_modules=allowed_modules,
        )
        max_chars = self._settings.max_response_chars
        emitted_chars = 0
        truncated = False
        done_yielded = False

        try:
            async for msg in _open_query_stream(prompt, options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            if truncated:
                                continue
                            text = block.text
                            remaining = max_chars - emitted_chars
                            if remaining <= 0:
                                truncated = True
                                yield TextDeltaEvent(text=_TRUNCATION_NOTICE)
                                continue
                            if len(text) > remaining:
                                text = text[:remaining]
                                truncated = True
                                emitted_chars += len(text)
                                yield TextDeltaEvent(text=text)
                                yield TextDeltaEvent(text=_TRUNCATION_NOTICE)
                                continue
                            emitted_chars += len(text)
                            yield TextDeltaEvent(text=text)
                        elif isinstance(block, ThinkingBlock):
                            yield ThinkingDeltaEvent(text=block.thinking)
                        elif isinstance(block, ToolUseBlock):
                            yield ToolUseEvent(
                                id=block.id,
                                name=block.name,
                                input=dict(block.input),
                            )
                elif isinstance(msg, UserMessage):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            yield ToolResultEvent(
                                tool_use_id=block.tool_use_id,
                                is_error=bool(block.is_error),
                            )
                elif isinstance(msg, ResultMessage):
                    done_yielded = True
                    yield DoneEvent(
                        usage=msg.usage,
                        cost_usd=msg.total_cost_usd,
                    )
        except Exception as e:  # noqa: BLE001
            if done_yielded:
                log.info("agent_subprocess_cleanup_noise error=%s", e)
                return
            log.exception("agent_turn_failed")
            yield ErrorEvent(message=str(e))
