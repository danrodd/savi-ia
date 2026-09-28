"""Generación del auto-título con la Responses API.

Una sola llamada, sin tools y sin streaming. Ante cualquier error devuelve
`None` (contrato del puerto): el título provisional queda como está.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable
from typing import Any, Protocol, cast

from openai import AsyncOpenAI

from app.infrastructure.config import Settings
from app.modules.chat.domain.interfaces import ActiveProvider, TitleGenerator
from app.modules.chat.infrastructure.llm.title_prompt import (
    TITLE_MAX_OUTPUT_TOKENS,
    TITLE_SYSTEM_PROMPT,
    build_title_prompt,
    clean_title,
)

log = logging.getLogger(__name__)


class _Responses(Protocol):
    def create(self, **kwargs: Any) -> Awaitable[Any]: ...


class _Client(Protocol):
    responses: _Responses


class OpenAITitleGenerator(TitleGenerator):
    def __init__(
        self,
        settings: Settings,
        provider: ActiveProvider,
        *,
        client: _Client | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._client = client

    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        client = cast(_Client, self._client or AsyncOpenAI(api_key=self._provider.credential))
        try:
            result = client.responses.create(
                model=self._provider.title_model,
                instructions=TITLE_SYSTEM_PROMPT,
                input=build_title_prompt(user_msg, assistant_msg),
                max_output_tokens=TITLE_MAX_OUTPUT_TOKENS,
                store=False,
            )
            response = await result if inspect.isawaitable(result) else result
            if getattr(response, "status", None) == "incomplete":
                # Un pedazo de título es peor que el provisional: no se guarda.
                log.warning("openai_title_incomplete model=%s", self._provider.title_model)
                return None
            return clean_title(_output_text(response))
        except Exception:  # noqa: BLE001
            log.exception("openai_title_generation_failed")
            return None


def _output_text(response: Any) -> str:
    """`output_text` es la propiedad de conveniencia de la SDK; los dobles
    de test solo exponen el texto crudo."""
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text
    return ""
