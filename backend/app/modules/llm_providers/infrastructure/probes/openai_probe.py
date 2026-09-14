"""Prueba de credencial de OpenAI y listado de modelos disponibles.

Usamos `GET /v1/models`, que responde para cualquier API key válida y no
consume tokens. El endpoint no garantiza qué modelos soportan cada
capacidad, así que filtramos solo las familias claramente no
conversacionales y conservamos los IDs desconocidos: una whitelist
cerrada se rompe cada vez que OpenAI publica un modelo nuevo.

Cuando el formulario ya eligió un modelo, además se ejecuta una solicitud
mínima de Responses: es la única forma de detectar un modelo que figura en
el catálogo pero no está habilitado para esta cuenta.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from openai import APIStatusError, AsyncOpenAI

from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import ProbeResult, ProviderProbe
from app.modules.llm_providers.domain.value_objects import ModelInfo

log = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 90
_AUTH_STATUS = (401, 403)
_MODEL_UNAVAILABLE_STATUS = (400, 404)
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


class _Responses(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class _OpenAIClient(Protocol):
    @property
    def models(self) -> _Models: ...

    @property
    def responses(self) -> _Responses: ...


ClientFactory = Callable[[str], _OpenAIClient]


def _quota_exhausted(error: APIStatusError) -> bool:
    """`429` por saldo agotado no es un límite temporal: reintentar no ayuda.

    OpenAI lo devuelve con `code=credit_balance_exhausted` y
    `type=insufficient_quota` dentro del body, no en `error.code`.
    """
    body: object = error.body
    if isinstance(body, dict):
        data = cast("dict[str, object]", body)
        code = data.get("code")
        etype = data.get("type")
        if code in ("credit_balance_exhausted", "insufficient_quota"):
            return True
        if etype == "insufficient_quota":
            return True
    return getattr(error, "code", None) in (
        "credit_balance_exhausted",
        "insufficient_quota",
    )


class OpenAIProbe(ProviderProbe):
    def __init__(self, *, client_factory: ClientFactory | None = None) -> None:
        self._client_factory = client_factory

    def _client(self, credential: str) -> _OpenAIClient:
        if self._client_factory is None:
            return cast(_OpenAIClient, AsyncOpenAI(api_key=credential))
        factory = self._client_factory
        return factory(credential)

    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        client = self._client(config.credential or "")
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
                return await self._fetch_models(client)
        except Exception:  # noqa: BLE001
            log.exception("openai_model_listing_failed")
            return []

    async def _fetch_models(self, client: _OpenAIClient) -> list[ModelInfo]:
        page = await client.models.list()
        models: list[ModelInfo] = []
        for model in page.data:
            model_id = str(getattr(model, "id", "") or "")
            if not model_id or _NON_CONVERSATIONAL.search(model_id):
                continue
            models.append(ModelInfo(id=model_id, display_name=model_id))
        models.sort(key=lambda m: (m.display_name.lower(), m.id))
        return models

    async def _validate_model(self, client: _OpenAIClient, model: str) -> None:
        await client.responses.create(
            model=model,
            input="ping",
            max_output_tokens=16,
            store=False,
        )

    async def test(self, config: LlmProviderConfig) -> ProbeResult:
        client = self._client(config.credential or "")
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
                models = await self._fetch_models(client)
                if config.chat_model:
                    await self._validate_model(client, config.chat_model)
        except TimeoutError:
            return ProbeResult(
                ok=False,
                detail="OpenAI no respondió a tiempo. Revisá la conexión a internet.",
            )
        except APIStatusError as error:
            if error.status_code in _AUTH_STATUS:
                return ProbeResult(
                    ok=False,
                    detail="La API key de OpenAI no es válida o no tiene permisos.",
                )
            if error.status_code == 429:
                if _quota_exhausted(error):
                    return ProbeResult(
                        ok=False,
                        detail=(
                            "La cuenta de OpenAI no tiene créditos. Cargá saldo en la "
                            "plataforma de OpenAI para poder usar el chat."
                        ),
                    )
                return ProbeResult(
                    ok=False,
                    detail="OpenAI rechazó la solicitud por límite de uso. Intentá de nuevo.",
                )
            if error.status_code in _MODEL_UNAVAILABLE_STATUS and config.chat_model:
                return ProbeResult(
                    ok=False,
                    detail=(
                        f"El modelo '{config.chat_model}' no está disponible para esta "
                        "cuenta. Elegí otro de la lista."
                    ),
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
