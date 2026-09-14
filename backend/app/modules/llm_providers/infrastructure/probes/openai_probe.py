"""Prueba de credencial de OpenAI y listado de modelos disponibles.

Usamos `GET /v1/models`, que responde para cualquier API key válida y no
consume tokens. El endpoint no garantiza qué modelos soportan cada
capacidad, así que filtramos solo las familias claramente no
conversacionales y conservamos los IDs desconocidos: una whitelist
cerrada se rompe cada vez que OpenAI publica un modelo nuevo.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from typing import Protocol, cast

from openai import APIStatusError, AsyncOpenAI

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import ProbeResult, ProviderProbe
from app.modules.llm_providers.domain.value_objects import ModelInfo

log = logging.getLogger(__name__)

_AUTH_STATUS = (401, 403)
# Familias que no atienden una conversación de texto con tools. Es una
# lista de *exclusión*, no de inclusión: preferimos ofrecer un modelo
# nuevo de más que ocultar uno válido.
_NON_CONVERSATIONAL = re.compile(
    r"(embedding|embed-|-embed|whisper|tts|transcribe|dall-e|sora|"
    r"image|audio|realtime|moderation|davinci|babbage|ada|curie|"
    r"codex-mini|computer-use)",
    re.IGNORECASE,
)


class _ModelPage(Protocol):
    @property
    def data(self) -> Sequence[object]: ...


class _Models(Protocol):
    async def list(self) -> _ModelPage: ...


class _OpenAIClient(Protocol):
    @property
    def models(self) -> _Models: ...


ClientFactory = Callable[[str], _OpenAIClient]


class OpenAIProbe(ProviderProbe):
    def __init__(self, *, client_factory: ClientFactory | None = None) -> None:
        self._client_factory = client_factory

    def _client(self, credential: str) -> _OpenAIClient:
        if self._client_factory is None:
            return cast(_OpenAIClient, AsyncOpenAI(api_key=credential))
        factory = self._client_factory
        return factory(credential)

    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        try:
            return await self._fetch_models(config)
        except Exception:  # noqa: BLE001
            log.exception("openai_model_listing_failed")
            return []

    async def _fetch_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        page = await self._client(config.credential or "").models.list()
        models: list[ModelInfo] = []
        for model in page.data:
            model_id = str(getattr(model, "id", "") or "")
            if not model_id or _NON_CONVERSATIONAL.search(model_id):
                continue
            models.append(ModelInfo(id=model_id, display_name=model_id))
        models.sort(key=lambda m: (m.display_name.lower(), m.id))
        return models

    async def test(self, config: LlmProviderConfig) -> ProbeResult:
        try:
            models = await self._fetch_models(config)
        except APIStatusError as error:
            if error.status_code in _AUTH_STATUS:
                return ProbeResult(
                    ok=False,
                    detail="La API key de OpenAI no es válida o no tiene permisos.",
                )
            if error.status_code == 429:
                return ProbeResult(
                    ok=False,
                    detail="OpenAI rechazó la solicitud por límite de uso. Intentá de nuevo.",
                )
            return ProbeResult(
                ok=False,
                detail="OpenAI devolvió un error al validar la credencial.",
            )
        except Exception:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                detail="No se pudo conectar con OpenAI. Revisá la conexión a internet.",
            )
        return ProbeResult(
            ok=True,
            detail="La API key de OpenAI es válida. Elegí un modelo de la lista.",
            models=tuple(models),
        )
