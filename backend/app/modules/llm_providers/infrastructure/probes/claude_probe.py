"""Prueba de credencial de Claude: un turno mínimo del SDK.

Sin tools, `max_turns=1` y con el modelo de títulos (el barato). El SDK
no tiene un endpoint para listar modelos, así que `models` queda vacío y
la UI pide el ID a mano.
"""
from __future__ import annotations

import asyncio
import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from app.infrastructure.claude_cli import resolve_cli_path
from app.infrastructure.claude_env import build_claude_env
from app.infrastructure.config import Settings
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import ProbeResult, ProviderProbe
from app.modules.llm_providers.domain.value_objects import ModelInfo

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 90
_CREDENTIAL_HINTS = ("401", "invalid api key", "authentication", "oauth", "unauthorized")


class ClaudeProbe(ProviderProbe):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def test(self, config: LlmProviderConfig) -> ProbeResult:
        options = ClaudeAgentOptions(
            model=config.title_model,
            system_prompt="Respondé únicamente con la palabra: ok",
            allowed_tools=[],
            permission_mode="bypassPermissions",
            max_turns=1,
            cli_path=resolve_cli_path(),
            env=build_claude_env(
                credential_kind=config.credential_kind.value,
                credential=config.credential,
                git_bash_path=self._settings.claude_code_git_bash_path,
            ),
        )
        text: list[str] = []
        result: ResultMessage | None = None
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
                async for msg in query(prompt="ping", options=options):
                    if isinstance(msg, AssistantMessage):
                        text.extend(b.text for b in msg.content if isinstance(b, TextBlock))
                    elif isinstance(msg, ResultMessage):
                        result = msg
        except TimeoutError:
            return ProbeResult(
                ok=False,
                detail="Claude no respondió a tiempo. Revisá la conexión a internet.",
            )
        except Exception as e:  # noqa: BLE001
            # `result` ya llegó: el error es ruido del cierre del subproceso.
            if result is None:
                logger.warning("claude_probe_failed error=%s", e)
                return ProbeResult(ok=False, detail=_detail_for(str(e)))

        if result is None or result.is_error:
            return ProbeResult(ok=False, detail=_detail_for(" ".join(text)))
        return ProbeResult(ok=True, detail=f"Claude respondió con el modelo {config.title_model}.")

    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        return []


def _detail_for(message: str) -> str:
    lowered = message.lower()
    if any(hint in lowered for hint in _CREDENTIAL_HINTS):
        return "La credencial de Claude no es válida o venció."
    if "model" in lowered:
        return "Claude rechazó el modelo configurado. Revisá el ID del modelo de títulos."
    detail = message.strip()[:300]
    return f"No se pudo usar Claude: {detail}" if detail else "No se pudo usar Claude."
