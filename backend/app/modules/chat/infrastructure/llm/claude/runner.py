"""Runner del agente SAVI sobre el Claude Agent SDK.

Cada turno construye las tools neutrales y un MCP server in-process nuevo
(las clausuras atan el contexto del turno) y emite eventos tipados listos
para serializar como SSE.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    Message,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from app.infrastructure.claude_cli import resolve_cli_path
from app.infrastructure.claude_env import build_claude_env
from app.infrastructure.config import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    ThinkingDeltaEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import ActiveProvider, LLMRunner
from app.modules.chat.infrastructure.llm.claude.mcp_adapter import (
    BUILTIN_TOOLS,
    MCP_SERVER_NAME,
    allowed_tool_names,
    build_mcp_server,
)
from app.modules.chat.infrastructure.llm.errors import user_facing_error
from app.modules.chat.infrastructure.llm.system_prompt import SYSTEM_PROMPT
from app.modules.chat.infrastructure.llm.tools.registry import build_savi_tools
from app.modules.chat.infrastructure.llm.truncation import ResponseTruncator
from app.modules.company_knowledge.domain.services import TurnDocumentContext

log = logging.getLogger(__name__)

CREDENTIAL_REMEDY = (
    "La credencial de Claude venció o no es válida. Para renovarla, abrí "
    "'Iniciar sesión en Claude' desde el menú Inicio y volvé a intentar."
)


def _log_cli_stderr(line: str) -> None:
    """Manda al log lo que el CLI escribe en stderr.

    El SDK sólo canaliza stderr si el llamador registra este callback; sin
    él lo deja ir al stderr del proceso padre, y SAVI empaquetado corre con
    `console=False`, o sea que no hay ninguno. El resultado era un error
    que decía textualmente "Check stderr output for details" sin que
    existiera un stderr donde mirar.
    """
    text = line.rstrip()
    if text:
        log.warning("claude_cli_stderr %s", text)


def _build_options(
    settings: Settings,
    provider: ActiveProvider,
    *,
    conversation_id: UUID | None,
    allowed_modules: frozenset[ModuleCode] | None,
    erp_database_id: UUID | None,
    document_context: TurnDocumentContext | None,
) -> ClaudeAgentOptions:
    tools = build_savi_tools(
        conversation_id=conversation_id,
        allowed_modules=allowed_modules,
        erp_database_id=erp_database_id,
        document_context=document_context,
    )
    return ClaudeAgentOptions(
        model=provider.chat_model,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={MCP_SERVER_NAME: build_mcp_server(tools)},
        # `tools=[]` apaga TODAS las herramientas integradas del CLI. NO es
        # redundante con `allowed_tools`: esa lista solo evita el prompt de
        # permiso, no define qué existe. Sin esto el CLI arranca con Bash,
        # Read, Write y WebFetch entre otras, y `bypassPermissions` las
        # aprueba solas: cualquier usuario del chat podía pedir que se
        # leyera el `.env` de la máquina donde corre SAVI.
        tools=[],
        allowed_tools=allowed_tool_names(tools),
        disallowed_tools=list(BUILTIN_TOOLS),
        permission_mode="bypassPermissions",
        max_turns=settings.max_agent_turns,
        # Por el ejecutable y no por el shim `.cmd` de npm: ver
        # `resolve_cli_path`. El system prompt viaja por argv y no entra
        # en el límite de cmd.exe.
        cli_path=resolve_cli_path(),
        stderr=_log_cli_stderr,
        # La credencial viaja por consulta y no por `os.environ`: cambiarla
        # desde administración aplica al turno siguiente sin reiniciar.
        env=build_claude_env(
            credential_kind=provider.credential_kind,
            credential=provider.credential,
            git_bash_path=settings.claude_code_git_bash_path,
        ),
    )


async def _open_query_stream(prompt: str, options: ClaudeAgentOptions) -> AsyncIterator[Message]:
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
    def __init__(self, settings: Settings, provider: ActiveProvider) -> None:
        self._settings = settings
        self._provider = provider

    async def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
    ) -> AsyncIterator[ChatEvent]:
        options = _build_options(
            self._settings,
            self._provider,
            conversation_id=conversation_id,
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
            document_context=document_context,
        )
        truncator = ResponseTruncator(self._settings.max_response_chars)
        done_yielded = False

        try:
            async for msg in _open_query_stream(prompt, options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            for event in truncator.feed(block.text):
                                yield event
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
                        provider=self._provider.kind,
                        model=self._provider.chat_model,
                    )
        except Exception as e:  # noqa: BLE001
            if done_yielded:
                log.info("agent_subprocess_cleanup_noise error=%s", e)
                return
            log.exception("agent_turn_failed")
            yield ErrorEvent(message=user_facing_error(str(e), credential_remedy=CREDENTIAL_REMEDY))
