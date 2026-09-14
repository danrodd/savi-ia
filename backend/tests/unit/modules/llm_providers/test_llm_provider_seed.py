"""El seed cubre los tres `credential_kind` posibles desde el `.env`,
es idempotente y nunca pisa una tabla con datos previos."""
from __future__ import annotations

from app.infrastructure.config.settings import Settings
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import LlmProviderRepository
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind
from app.modules.llm_providers.infrastructure.seed import seed_llm_providers


class _FakeRepository(LlmProviderRepository):
    def __init__(self, *, preloaded: bool = False) -> None:
        self.saved: LlmProviderConfig | None = None
        self._count = 1 if preloaded else 0

    async def get(self, provider: ProviderKind) -> LlmProviderConfig | None:
        return None

    async def get_active(self) -> LlmProviderConfig | None:
        return None

    async def list_all(self) -> list[LlmProviderConfig]:
        return []

    async def count(self) -> int:
        return self._count

    async def save(self, config: LlmProviderConfig) -> None:
        self.saved = config
        self._count += 1

    async def activate(self, provider: ProviderKind) -> None:  # pragma: no cover
        pass


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


async def test_oauth_token_takes_priority() -> None:
    repo = _FakeRepository()
    settings = _settings(
        claude_code_oauth_token="tok-123", anthropic_api_key="sk-should-be-ignored"
    )

    await seed_llm_providers(repo, settings)

    assert repo.saved is not None
    assert repo.saved.credential_kind == CredentialKind.OAUTH_TOKEN
    assert repo.saved.credential == "tok-123"
    assert repo.saved.is_active is True


async def test_api_key_when_no_oauth_token() -> None:
    repo = _FakeRepository()
    settings = _settings(claude_code_oauth_token="", anthropic_api_key="sk-abc")

    await seed_llm_providers(repo, settings)

    assert repo.saved is not None
    assert repo.saved.credential_kind == CredentialKind.API_KEY
    assert repo.saved.credential == "sk-abc"


async def test_local_session_without_any_credential() -> None:
    repo = _FakeRepository()
    settings = _settings(claude_code_oauth_token="", anthropic_api_key="")

    await seed_llm_providers(repo, settings)

    assert repo.saved is not None
    assert repo.saved.credential_kind == CredentialKind.LOCAL_SESSION
    assert repo.saved.credential is None


async def test_does_not_overwrite_a_table_with_existing_rows() -> None:
    repo = _FakeRepository(preloaded=True)
    settings = _settings(claude_code_oauth_token="tok-123")

    await seed_llm_providers(repo, settings)

    assert repo.saved is None
