"""Compuerta del CLI de Claude (`local_session`): la habilita SEO Group por cliente.

Con la compuerta cerrada la opción no se ofrece, no se puede guardar ni activar, y una sesión
local que ya estaba en uso deja de resolverse en el turno siguiente.
"""

from __future__ import annotations

import pytest

from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.llm_providers.application.dtos import SaveLlmProviderDTO
from app.modules.llm_providers.application.use_cases import ManageLlmProvidersUseCase
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.active_provider_resolver import (
    CachedActiveProviderResolver,
)
from app.shared.exceptions import ValidationError

from .test_manage_llm_providers import (  # pyright: ignore[reportPrivateUsage]
    _FakeClaudeProbe,
    _FakeRepository,
)


class _Gate:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    async def __call__(self) -> bool:
        return self.allowed


def _use_case(gate: _Gate) -> tuple[ManageLlmProvidersUseCase, _FakeRepository]:
    repo = _FakeRepository()
    use_case = ManageLlmProvidersUseCase(
        repo,
        probes={ProviderKind.CLAUDE: _FakeClaudeProbe()},
        on_change=lambda: None,
        local_cli_allowed=gate,
    )
    return use_case, repo


def _local_session() -> SaveLlmProviderDTO:
    return SaveLlmProviderDTO(
        credential_kind=CredentialKind.LOCAL_SESSION.value,
        chat_model="claude-sonnet-4-6",
        title_model="claude-haiku-4-5",
    )


async def test_the_option_is_offered_only_when_allowed() -> None:
    gate = _Gate(allowed=True)
    use_case, _ = _use_case(gate)

    claude = next(p for p in await use_case.list() if p.provider == "claude")
    assert "local_session" in claude.credential_kinds

    gate.allowed = False
    claude = next(p for p in await use_case.list() if p.provider == "claude")
    assert "local_session" not in claude.credential_kinds
    assert "api_key" in claude.credential_kinds


async def test_saving_a_local_session_is_rejected_when_not_allowed() -> None:
    use_case, repo = _use_case(_Gate(allowed=False))

    with pytest.raises(ValidationError, match="SEO Group"):
        await use_case.save("claude", _local_session())

    assert await repo.get(ProviderKind.CLAUDE) is None


async def test_an_api_key_is_always_saved() -> None:
    use_case, _ = _use_case(_Gate(allowed=False))

    dto = await use_case.save(
        "claude",
        SaveLlmProviderDTO(
            credential_kind=CredentialKind.API_KEY.value,
            credential="sk-ant-123",
            chat_model="claude-sonnet-4-6",
            title_model="claude-haiku-4-5",
        ),
    )

    assert dto.has_credential is True


async def test_activating_a_stored_local_session_is_rejected_when_not_allowed() -> None:
    gate = _Gate(allowed=True)
    use_case, _ = _use_case(gate)
    await use_case.save("claude", _local_session())
    gate.allowed = False

    with pytest.raises(ValidationError, match="SEO Group"):
        await use_case.activate("claude")


async def test_the_resolver_stops_serving_a_local_session_when_the_permission_is_revoked() -> None:
    gate = _Gate(allowed=True)
    repo = _FakeRepository()
    await repo.save(
        LlmProviderConfig(
            provider=ProviderKind.CLAUDE,
            credential_kind=CredentialKind.LOCAL_SESSION,
            credential=None,
            chat_model="claude-sonnet-4-6",
            title_model="claude-haiku-4-5",
            is_active=True,
        )
    )
    resolver = CachedActiveProviderResolver(repo, gate)

    assert (await resolver.resolve()).credential_kind == "local_session"

    gate.allowed = False
    with pytest.raises(LlmProviderUnavailableError, match="SEO Group"):
        await resolver.resolve()  # aunque la configuración esté en la caché


async def test_the_resolver_never_blocks_an_api_key() -> None:
    repo = _FakeRepository()
    await repo.save(
        LlmProviderConfig(
            provider=ProviderKind.CLAUDE,
            credential_kind=CredentialKind.API_KEY,
            credential="sk-ant-123",
            chat_model="claude-sonnet-4-6",
            title_model="claude-haiku-4-5",
            is_active=True,
        )
    )

    resolver = CachedActiveProviderResolver(repo, _Gate(allowed=False))

    assert (await resolver.resolve()).credential_kind == "api_key"
