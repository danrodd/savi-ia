from __future__ import annotations

import logging
from collections.abc import AsyncIterable, Callable
from typing import Protocol, cast

from google import genai
from google.genai import errors

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import ProbeResult, ProviderProbe
from app.modules.llm_providers.domain.value_objects import ModelInfo

log = logging.getLogger(__name__)


class _Models(Protocol):
    async def list(self) -> AsyncIterable[object]: ...


class _AsyncClient(Protocol):
    models: _Models


class _Client(Protocol):
    aio: _AsyncClient


class GeminiProbe(ProviderProbe):
    def __init__(self, *, client_factory: Callable[[str], _Client] | None = None) -> None:
        self._client_factory = client_factory

    def _client(self, credential: str) -> _Client:
        if self._client_factory is None:
            return cast(_Client, genai.Client(api_key=credential))
        factory = self._client_factory
        return factory(credential)

    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        try:
            return await self._fetch_models(config)
        except Exception:  # noqa: BLE001
            log.exception("gemini_model_listing_failed")
            return []

    async def _fetch_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        pager = await self._client(config.credential or "").aio.models.list()
        models: list[ModelInfo] = []
        async for model in pager:
            actions = cast(list[str], getattr(model, "supported_actions", None) or [])
            if "generateContent" not in actions:
                continue
            name = str(getattr(model, "name", "") or "")
            model_id = name.removeprefix("models/")
            if model_id:
                models.append(
                    ModelInfo(
                        id=model_id,
                        display_name=str(getattr(model, "display_name", model_id)),
                    )
                )
        return models

    async def test(self, config: LlmProviderConfig) -> ProbeResult:
        try:
            models = await self._fetch_models(config)
            return ProbeResult(
                ok=True,
                detail="La API key de Gemini es válida.",
                models=tuple(models),
            )
        except errors.ClientError as error:
            if error.code in (401, 403):
                return ProbeResult(
                    ok=False,
                    detail="La API key de Gemini no es válida o no tiene permisos.",
                )
            return ProbeResult(ok=False, detail="No se pudo probar Gemini.")
        except Exception:  # noqa: BLE001
            return ProbeResult(ok=False, detail="No se pudo probar Gemini.")
