from __future__ import annotations

import logging
from typing import Any, Protocol, cast

from google import genai
from google.genai import types

from app.infrastructure.config import Settings
from app.modules.chat.domain.interfaces import ActiveProvider, TitleGenerator
from app.modules.chat.infrastructure.llm.title_prompt import (
    TITLE_MAX_OUTPUT_TOKENS,
    TITLE_SYSTEM_PROMPT,
    build_title_prompt,
    clean_title,
)

log = logging.getLogger(__name__)


class _TitleModels(Protocol):
    async def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse: ...


class _TitleAsyncClient(Protocol):
    models: _TitleModels


class _TitleClient(Protocol):
    aio: _TitleAsyncClient


class GeminiTitleGenerator(TitleGenerator):
    def __init__(
        self,
        settings: Settings,
        provider: ActiveProvider,
        *,
        client: _TitleClient | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._client = client

    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        client = cast(
            _TitleClient,
            self._client or genai.Client(api_key=self._provider.credential),
        )
        try:
            response = await client.aio.models.generate_content(
                model=self._provider.title_model,
                contents=build_title_prompt(user_msg, assistant_msg),
                config=types.GenerateContentConfig(
                    system_instruction=TITLE_SYSTEM_PROMPT,
                    max_output_tokens=TITLE_MAX_OUTPUT_TOKENS,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            if _was_cut(response):
                log.warning("gemini_title_incomplete model=%s", self._provider.title_model)
                return None
            return clean_title(response.text or "")
        except Exception:  # noqa: BLE001
            log.exception("gemini_title_generation_failed")
            return None


def _was_cut(response: Any) -> bool:
    """Un pedazo de título es peor que el provisional: no se guarda."""
    candidates: list[Any] = list(getattr(response, "candidates", None) or [])
    if not candidates:
        return False
    reason = getattr(candidates[0], "finish_reason", None)
    return str(getattr(reason, "name", reason)) == "MAX_TOKENS"
