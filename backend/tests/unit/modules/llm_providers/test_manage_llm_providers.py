"""`ManageLlmProvidersUseCase` con un repositorio en memoria (fake).

No hace falta SQLite acá: lo que se prueba son las reglas de negocio
(credencial vacía = conservar, activar exige config usable, proveedor no
implementado da 422), no el motor de persistencia.
"""
from __future__ import annotations

import pytest

from app.modules.llm_providers.application.dtos import SaveLlmProviderDTO
from app.modules.llm_providers.application.use_cases import ManageLlmProvidersUseCase
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import (
    LlmProviderRepository,
    ProbeResult,
    ProviderProbe,
)
from app.modules.llm_providers.domain.value_objects import (
    CredentialKind,
    ModelInfo,
    ProviderKind,
)
from app.shared.exceptions import ValidationError


class _FakeRepository(LlmProviderRepository):
    def __init__(self) -> None:
        self._rows: dict[ProviderKind, LlmProviderConfig] = {}

    async def get(self, provider: ProviderKind) -> LlmProviderConfig | None:
        return self._rows.get(provider)

    async def get_active(self) -> LlmProviderConfig | None:
        for row in self._rows.values():
            if row.is_active:
                return row
        return None

    async def list_all(self) -> list[LlmProviderConfig]:
        return list(self._rows.values())

    async def count(self) -> int:
        return len(self._rows)

    async def save(self, config: LlmProviderConfig) -> None:
        self._rows[config.provider] = config

    async def activate(self, provider: ProviderKind) -> None:
        for kind, row in self._rows.items():
            row.is_active = kind == provider


class _FakeClaudeProbe(ProviderProbe):
    async def test(self, config: LlmProviderConfig) -> ProbeResult:
        if config.credential == "bad":
            return ProbeResult(ok=False, detail="credencial inválida")
        return ProbeResult(ok=True, detail="ok")

    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        return []


def _use_case() -> tuple[ManageLlmProvidersUseCase, _FakeRepository, list[int]]:
    repo = _FakeRepository()
    calls: list[int] = []
    use_case = ManageLlmProvidersUseCase(
        repo,
        probes={ProviderKind.CLAUDE: _FakeClaudeProbe()},
        on_change=lambda: calls.append(1),
    )
    return use_case, repo, calls


def _dto(**overrides: object) -> SaveLlmProviderDTO:
    base: dict[str, object] = {
        "credential_kind": CredentialKind.API_KEY.value,
        "credential": "sk-ant-123",
        "chat_model": "claude-sonnet-4-6",
        "title_model": "claude-haiku-4-5",
    }
    base.update(overrides)
    return SaveLlmProviderDTO(**base)  # type: ignore[arg-type]


async def test_list_includes_every_descriptor_even_unconfigured() -> None:
    use_case, _, _ = _use_case()

    items = await use_case.list()

    kinds = {item.provider for item in items}
    assert kinds == {"claude", "gemini", "openai"}


async def test_save_never_leaks_the_credential_in_the_dto() -> None:
    use_case, _, calls = _use_case()

    dto = await use_case.save("claude", _dto())

    assert not hasattr(dto, "credential")
    assert dto.has_credential is True
    assert calls == [1]


async def test_empty_credential_keeps_the_stored_one() -> None:
    use_case, repo, _ = _use_case()
    await use_case.save("claude", _dto())

    await use_case.save("claude", _dto(credential=""))

    stored = await repo.get(ProviderKind.CLAUDE)
    assert stored is not None
    assert stored.credential == "sk-ant-123"


async def test_test_allows_empty_models_before_catalog_selection() -> None:
    use_case, _, _ = _use_case()

    result = await use_case.test("claude", _dto(chat_model="", title_model=""))

    assert result.ok is True


async def test_activate_without_credential_is_rejected() -> None:
    use_case, repo, _ = _use_case()
    await repo.save(
        LlmProviderConfig(
            provider=ProviderKind.CLAUDE,
            credential_kind=CredentialKind.API_KEY,
            credential=None,
            chat_model="claude-sonnet-4-6",
            title_model="claude-haiku-4-5",
        )
    )

    with pytest.raises(ValidationError):
        await use_case.activate("claude")


async def test_saving_an_active_provider_without_models_says_so() -> None:
    """El mensaje tiene que nombrar lo que falta.

    Decía siempre "sin credencial", y con `local_session` — que por
    definición no lleva credencial — mandaba a buscar donde no estaba el
    problema: lo que faltaban eran los IDs de modelo.
    """
    use_case, repo, _ = _use_case()
    await repo.save(
        LlmProviderConfig(
            provider=ProviderKind.CLAUDE,
            credential_kind=CredentialKind.LOCAL_SESSION,
            credential=None,
            chat_model="claude-sonnet-5",
            title_model="claude-haiku-4-5",
            is_active=True,
        )
    )

    with pytest.raises(ValidationError, match="modelo de chat"):
        await use_case.save(
            "claude",
            _dto(credential_kind="local_session", chat_model="", title_model=""),
        )


async def test_activate_ok_invalidates_the_resolver_cache() -> None:
    use_case, repo, calls = _use_case()
    await repo.save(
        LlmProviderConfig(
            provider=ProviderKind.CLAUDE,
            credential_kind=CredentialKind.API_KEY,
            credential="sk-ant-123",
            chat_model="claude-sonnet-4-6",
            title_model="claude-haiku-4-5",
        )
    )
    calls.clear()

    await use_case.activate("claude")

    assert calls == [1]


async def test_gemini_provider_is_implemented() -> None:
    use_case, _, _ = _use_case()

    saved = await use_case.save("gemini", _dto())
    assert saved.provider == "gemini"


async def test_unsupported_credential_kind_is_rejected() -> None:
    use_case, _, _ = _use_case()

    with pytest.raises(ValidationError):
        await use_case.save("claude", _dto(credential_kind="not-a-kind"))


async def test_document_model_is_saved_kept_when_omitted_and_cleared_when_empty() -> None:
    use_case, repo, _ = _use_case()

    await use_case.save("claude", _dto(document_model="claude-sonnet-5"))
    stored = await repo.get(ProviderKind.CLAUDE)
    assert stored is not None and stored.document_model == "claude-sonnet-5"

    # Omitido (`None`): conserva el guardado, como la credencial.
    dto = await use_case.save("claude", _dto(credential=""))
    assert dto.document_model == "claude-sonnet-5"

    # Vacío: vuelve a usar el modelo de chat.
    await use_case.save("claude", _dto(credential="", document_model=""))
    stored = await repo.get(ProviderKind.CLAUDE)
    assert stored is not None and stored.document_model is None
