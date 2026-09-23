"""La cache del resolver sirve una sola lectura a BD por varias
resoluciones, y `invalidate()` (llamado por `save`/`activate`) fuerza
la próxima a ir de nuevo a BD."""
from __future__ import annotations

import asyncio

import pytest

from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import LlmProviderRepository
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.active_provider_resolver import (
    CachedActiveProviderResolver,
)


class _CountingRepository(LlmProviderRepository):
    def __init__(self, active: LlmProviderConfig | None) -> None:
        self._active = active
        self.reads = 0

    async def get(self, provider: ProviderKind) -> LlmProviderConfig | None:
        return self._active if self._active and self._active.provider == provider else None

    async def get_active(self) -> LlmProviderConfig | None:
        self.reads += 1
        return self._active

    async def list_all(self) -> list[LlmProviderConfig]:
        return [self._active] if self._active else []

    async def count(self) -> int:
        return 1 if self._active else 0

    async def save(self, config: LlmProviderConfig) -> None:  # pragma: no cover
        self._active = config

    async def activate(self, provider: ProviderKind) -> None:  # pragma: no cover
        pass


def _config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=ProviderKind.CLAUDE,
        credential_kind=CredentialKind.API_KEY,
        credential="sk-ant-123",
        chat_model="claude-sonnet-4-6",
        title_model="claude-haiku-4-5",
        is_active=True,
    )


async def test_multiple_resolves_hit_the_repository_once() -> None:
    repo = _CountingRepository(_config())
    resolver = CachedActiveProviderResolver(repo)

    results = await asyncio.gather(*(resolver.resolve() for _ in range(5)))

    assert repo.reads == 1
    assert all(r.kind == "claude" for r in results)


async def test_invalidate_forces_a_fresh_read() -> None:
    repo = _CountingRepository(_config())
    resolver = CachedActiveProviderResolver(repo)
    await resolver.resolve()

    resolver.invalidate()
    await resolver.resolve()

    assert repo.reads == 2


async def test_without_active_provider_raises_unavailable() -> None:
    repo = _CountingRepository(None)
    resolver = CachedActiveProviderResolver(repo)

    with pytest.raises(LlmProviderUnavailableError):
        await resolver.resolve()


async def test_document_model_defaults_to_the_chat_model() -> None:
    resolver = CachedActiveProviderResolver(_CountingRepository(_config()))
    assert (await resolver.resolve()).document_model == "claude-sonnet-4-6"

    config = _config()
    config.document_model = "claude-haiku-4-5"
    resolver = CachedActiveProviderResolver(_CountingRepository(config))
    assert (await resolver.resolve()).document_model == "claude-haiku-4-5"
