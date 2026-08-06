"""Generación de títulos de conversación con modelo barato (Haiku).

Uso en dos fases:
- Fase 1: al recibir el primer turno (sólo `user_msg`) — título provisional.
- Fase 2: tras el turno completo (`user_msg` + `assistant_msg`) — refinado.

Ambas comparten el mismo system prompt: "máximo 5 palabras, español,
sin comillas ni punto final". Si la respuesta sale vacía o malformada,
devuelve `None` y dejamos el título actual de la conversación.
"""
from __future__ import annotations

import logging
import os

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from app.infrastructure.config import Settings

log = logging.getLogger(__name__)

_TITLE_SYSTEM = (
    "Eres un generador de títulos para una conversación con un asistente "
    "del ERP de SEO Group. Responde ÚNICAMENTE con un título muy corto "
    "(máximo 5 palabras, en español neutro de Colombia, sin comillas, "
    "sin punto final, sin emojis) que resuma la consulta del usuario. "
    "No saludes. No expliques. Solo el título."
)

_MAX_TITLE_LEN = 80
_ASSISTANT_PREVIEW_CHARS = 600


def _clean(raw: str) -> str:
    title = raw.strip().strip('"').strip("'").strip(".").strip()
    return title[:_MAX_TITLE_LEN]


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


async def generate_title(
    settings: Settings,
    user_msg: str,
    assistant_msg: str = "",
) -> str | None:
    """One-shot al modelo de títulos. Devuelve el título o `None` si vacío."""
    _apply_sdk_env(settings)
    options = ClaudeAgentOptions(
        model=settings.claude_title_model,
        system_prompt=_TITLE_SYSTEM,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        max_turns=1,
    )
    if assistant_msg.strip():
        prompt = (
            f"Usuario: {user_msg.strip()}\n\n"
            f"Asistente: {assistant_msg[:_ASSISTANT_PREVIEW_CHARS].strip()}\n\n"
            "Título:"
        )
    else:
        prompt = f"Usuario: {user_msg.strip()}\n\nTítulo:"

    parts: list[str] = []
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
    except Exception:
        log.exception("title_generation_failed")
        return None

    cleaned = _clean("".join(parts))
    return cleaned or None
