"""Seleccion del modelo/archivo ONNX de embeddings (variante int8 por defecto)."""

from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.config.settings import Settings
from app.modules.company_knowledge.infrastructure.embeddings import (
    FastEmbedEmbedder,
    default_model_file,
)
from app.modules.company_knowledge.infrastructure.embeddings import (
    fastembed_embedder as module,
)


def test_default_model_is_the_int8_variant() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.company_docs_embedding_model == "Xenova/multilingual-e5-small"
    assert settings.company_docs_embedding_model_file == ""
    assert default_model_file(settings.company_docs_embedding_model) == (
        "onnx/model_quantized.onnx"
    )


def test_fp32_variant_stays_registered_under_its_own_name() -> None:
    assert default_model_file("intfloat/multilingual-e5-small") == "onnx/model.onnx"
    assert default_model_file("otro/modelo") is None


@pytest.fixture
def registrations(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(module, "_registered_custom", set())
    monkeypatch.setattr(
        module.TextEmbedding, "add_custom_model", lambda **kwargs: calls.append(kwargs)
    )
    return calls


def test_registry_file_is_used_when_no_override(registrations: list[dict[str, Any]]) -> None:
    module._register_custom_if_needed("Xenova/multilingual-e5-small")

    assert registrations[0]["model_file"] == "onnx/model_quantized.onnx"


def test_settings_file_overrides_registry(registrations: list[dict[str, Any]]) -> None:
    module._register_custom_if_needed("Xenova/multilingual-e5-small", " onnx/model_q4.onnx ")

    assert registrations[0]["model_file"] == "onnx/model_q4.onnx"


def test_e5_prefixes_apply_to_the_quantized_model_name() -> None:
    embedder = FastEmbedEmbedder("Xenova/multilingual-e5-small", Path("."), 1)

    assert embedder._uses_e5 is True  # noqa: SLF001
