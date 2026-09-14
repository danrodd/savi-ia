"""DI del módulo `llm_providers`."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.llm_providers.application.use_cases import ManageLlmProvidersUseCase
from app.modules.llm_providers.domain.interfaces import LlmProviderRepository
from app.modules.llm_providers.domain.value_objects import ProviderKind
from app.modules.llm_providers.infrastructure.active_provider_resolver import (
    get_active_provider_resolver,
)
from app.modules.llm_providers.infrastructure.persistence import (
    SqlAlchemyLlmProviderRepository,
)
from app.modules.llm_providers.infrastructure.probes import ClaudeProbe, GeminiProbe
from app.shared.security import FernetCredentialCipher

SettingsDep = Annotated[Settings, Depends(get_settings)]


def build_llm_provider_repository(settings: Settings) -> LlmProviderRepository:
    """Misma clave que las bases del ERP: `ERP_CREDENTIALS_KEY` protege
    también las credenciales de IA."""
    cipher = FernetCredentialCipher(
        settings.erp_credentials_key,
        old_keys=[settings.erp_credentials_key_old],
    )
    return SqlAlchemyLlmProviderRepository(get_agent_sessionmaker(), cipher)


def get_manage_llm_providers_use_case(settings: SettingsDep) -> ManageLlmProvidersUseCase:
    return ManageLlmProvidersUseCase(
        build_llm_provider_repository(settings),
        probes={ProviderKind.CLAUDE: ClaudeProbe(settings), ProviderKind.GEMINI: GeminiProbe()},
        on_change=get_active_provider_resolver().invalidate,
    )


ManageLlmProvidersUseCaseDep = Annotated[
    ManageLlmProvidersUseCase, Depends(get_manage_llm_providers_use_case)
]
