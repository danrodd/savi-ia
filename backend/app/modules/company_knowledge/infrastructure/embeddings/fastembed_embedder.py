import logging
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

from app.modules.company_knowledge.domain.exceptions import EmbedderUnavailableError
from app.modules.company_knowledge.domain.interfaces import Embedder
from app.modules.company_knowledge.infrastructure.embeddings.vector_codec import (
    l2_normalize,
)

logger = logging.getLogger(__name__)

# Modelos que `fastembed` no trae de fábrica y hay que registrar antes de
# cargarlos. `multilingual-e5-small` es el candidato liviano del spike.
_CUSTOM_MODELS: dict[str, dict[str, Any]] = {
    "intfloat/multilingual-e5-small": {
        "dim": 384,
        "pooling": PoolingType.MEAN,
        "normalization": True,
        "model_file": "onnx/model.onnx",
    },
}
_registered_custom: set[str] = set()
# Tras un fallo de carga se reintenta pasado este tiempo: bajar el modelo
# después de arrancar no debería exigir reiniciar SAVI.
_RETRY_UNAVAILABLE_S = 60.0
_register_lock = threading.Lock()


def _register_custom_if_needed(model_name: str) -> None:
    spec = _CUSTOM_MODELS.get(model_name)
    if spec is None:
        return
    with _register_lock:
        if model_name in _registered_custom:
            return
        TextEmbedding.add_custom_model(
            model=model_name,
            pooling=spec["pooling"],
            normalization=spec["normalization"],
            sources=ModelSource(hf=model_name),
            dim=spec["dim"],
            model_file=spec["model_file"],
            description="Multilingual E5 small (384 dims)",
            license="MIT",
        )
        _registered_custom.add(model_name)


class FastEmbedEmbedder(Embedder):
    """Embeddings ONNX locales. Carga diferida y única por proceso."""

    def __init__(self, model_name: str, model_dir: Path, threads: int) -> None:
        self._model_name = model_name
        self._model_dir = model_dir
        self._threads = threads
        self._model: TextEmbedding | None = None
        self._dimension: int | None = None
        self._available: bool | None = None
        self._failed_at = 0.0
        self._lock = threading.Lock()
        self._uses_e5 = "e5" in model_name.lower()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        self._ensure()
        return self._dimension or 0

    def is_available(self) -> bool:
        return self._ensure()

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._require()
        payload = [f"passage: {text}" for text in texts] if self._uses_e5 else list(texts)
        return [l2_normalize(vector).tolist() for vector in model.embed(payload)]

    def embed_query(self, text: str) -> list[float]:
        model = self._require()
        payload = f"query: {text}" if self._uses_e5 else text
        vector = next(iter(model.embed([payload])))
        return l2_normalize(vector).tolist()

    def _require(self) -> TextEmbedding:
        if not self._ensure() or self._model is None:
            raise EmbedderUnavailableError()
        return self._model

    def _ensure(self) -> bool:
        if self._available is not None and not self._should_retry():
            return self._available
        with self._lock:
            if self._available is not None and not self._should_retry():
                return self._available
            try:
                _register_custom_if_needed(self._model_name)
                model = TextEmbedding(
                    model_name=self._model_name,
                    cache_dir=str(self._model_dir),
                    threads=self._threads,
                    local_files_only=True,
                )
                probe: np.ndarray = next(iter(model.embed(["dimension probe"])))
                self._dimension = int(len(probe))
                self._model = model
                self._available = True
            except Exception:  # noqa: BLE001
                logger.exception(
                    "company_docs_embedder_unavailable model=%s dir=%s",
                    self._model_name,
                    self._model_dir,
                )
                self._available = False
                self._failed_at = time.monotonic()
        return self._available

    def _should_retry(self) -> bool:
        return (
            self._available is False and time.monotonic() - self._failed_at >= _RETRY_UNAVAILABLE_S
        )


def download_embedding_model(model_name: str, model_dir: Path) -> None:
    """Descarga (o verifica) el modelo en `model_dir`. Solo para CLI/dev."""
    model_dir.mkdir(parents=True, exist_ok=True)
    _register_custom_if_needed(model_name)
    model = TextEmbedding(
        model_name=model_name,
        cache_dir=str(model_dir),
        local_files_only=False,
    )
    next(iter(model.embed(["download probe"])))
