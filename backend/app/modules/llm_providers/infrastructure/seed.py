"""Siembra el proveedor Claude desde el `.env` al arrancar.

Las instalaciones existentes configuraban Claude por `.env`. Esa
configuración pasa a ser la fila activa de `llm_provider_configs`, y a
partir de ahí se administra desde la aplicación.

Idempotente por "la tabla está vacía", igual que el seed de
`erp_databases`: si el administrador reconfiguró desde la UI, reiniciar
no pisa nada. Es el **único** lugar que lee `CLAUDE_*` y
`ANTHROPIC_API_KEY` de `Settings`.
"""
from __future__ import annotations

import logging

from app.infrastructure.config.settings import Settings
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import LlmProviderRepository
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind

logger = logging.getLogger(__name__)


def claude_config_from_settings(settings: Settings) -> LlmProviderConfig:
    if settings.claude_code_oauth_token:
        kind, credential = CredentialKind.OAUTH_TOKEN, settings.claude_code_oauth_token
    elif settings.anthropic_api_key:
        kind, credential = CredentialKind.API_KEY, settings.anthropic_api_key
    else:
        # Sin credencial en el `.env`: el CLI usa `claude login`, que es
        # exactamente el comportamiento anterior.
        kind, credential = CredentialKind.LOCAL_SESSION, None
    return LlmProviderConfig(
        provider=ProviderKind.CLAUDE,
        credential_kind=kind,
        credential=credential,
        chat_model=settings.claude_model,
        title_model=settings.claude_title_model,
        is_active=True,
    )


async def seed_llm_providers(repository: LlmProviderRepository, settings: Settings) -> None:
    if await repository.count() > 0:
        return
    config = claude_config_from_settings(settings)
    await repository.save(config)
    logger.info(
        "Proveedor de IA sembrado desde .env: Claude (%s, modelo %s).",
        config.credential_kind.value,
        config.chat_model,
    )
