# ruff: noqa: E501 — script de spike.
"""Embedder de Gemini para el spike de embeddings en la nube.

NO es código de producción: vive en `scripts/` para medir calidad, velocidad
y límites de cuota antes de decidir si SAVI ofrece esta opción.

La API key sale de `GEMINI_API_KEY` o, si no está, del proveedor Gemini ya
configurado en SAVI (descifrado en memoria; nunca se imprime ni se guarda).
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from google import genai
from google.genai import errors, types

from app.modules.company_knowledge.domain.interfaces import Embedder

_BATCH = 100
_MAX_RETRIES = 8


@dataclass
class GeminiUsage:
    requests: int = 0
    texts: int = 0
    retries_429: int = 0
    waited_s: float = 0.0
    api_s: float = 0.0
    query_ms: list[float] = field(default_factory=list[float])


class GeminiEmbedder(Embedder):
    def __init__(self, model: str, api_key: str, dimensions: int = 768) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._dimensions = dimensions
        self.usage = GeminiUsage()

    @property
    def model_name(self) -> str:
        return f"gemini/{self._model}"

    @property
    def dimension(self) -> int:
        return self._dimensions

    def is_available(self) -> bool:
        return True

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            vectors.extend(self._embed(list(texts[start : start + _BATCH]), "RETRIEVAL_DOCUMENT"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        started = time.perf_counter()
        vector = self._embed([text], "RETRIEVAL_QUERY")[0]
        self.usage.query_ms.append((time.perf_counter() - started) * 1000)
        return vector

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        config = types.EmbedContentConfig(task_type=task, output_dimensionality=self._dimensions)
        for attempt in range(_MAX_RETRIES):
            started = time.perf_counter()
            try:
                response = self._client.models.embed_content(
                    model=self._model,
                    contents=texts,  # pyright: ignore[reportArgumentType]
                    config=config,
                )
            except errors.ClientError as error:
                if error.code != 429 or attempt == _MAX_RETRIES - 1:
                    raise
                delay = _retry_delay(error)
                self.usage.retries_429 += 1
                self.usage.waited_s += delay
                time.sleep(delay)
                continue
            self.usage.api_s += time.perf_counter() - started
            self.usage.requests += 1
            self.usage.texts += len(texts)
            matrix = np.array([e.values for e in response.embeddings or []], dtype=np.float32)
            if matrix.shape[0] != len(texts):
                raise RuntimeError(
                    f"{self._model} devolvió {matrix.shape[0]} vectores para {len(texts)} textos"
                )
            # Con dimensión reducida (MRL) los vectores no vienen normalizados.
            matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
            return matrix.tolist()
        raise RuntimeError("sin reintentos")


def _retry_delay(error: errors.ClientError) -> float:
    match = re.search(r"retryDelay['\"]?:\s*['\"](\d+(?:\.\d+)?)s", str(error.details))
    return float(match.group(1)) + 1 if match else 30.0


async def resolve_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    from app.infrastructure.config.settings import get_settings
    from app.infrastructure.database.pool import init_engines
    from app.infrastructure.database.session import get_agent_sessionmaker
    from app.modules.llm_providers.domain.value_objects import ProviderKind
    from app.modules.llm_providers.infrastructure.persistence.sqlalchemy_llm_provider_repository import (
        SqlAlchemyLlmProviderRepository,
    )
    from app.shared.security.fernet_credential_cipher import FernetCredentialCipher

    settings = get_settings()
    init_engines(settings)
    repo = SqlAlchemyLlmProviderRepository(
        get_agent_sessionmaker(),
        FernetCredentialCipher(
            settings.erp_credentials_key, old_keys=[settings.erp_credentials_key_old]
        ),
    )
    config = await repo.get(ProviderKind.GEMINI)
    if config is None or not config.credential:
        raise SystemExit("No hay key de Gemini: definí GEMINI_API_KEY o configurá Gemini en SAVI.")
    return config.credential
