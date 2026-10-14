"""¿Se puede usar el CLI de Claude con la cuenta de la persona (`local_session`)?

Dos condiciones, en este orden:

1. El despliegue lo permite (`LOCAL_CLI_ENABLED`). El Master lo apaga: el CLI correría con la
   cuenta del servidor.
2. Si la instalación está vinculada a SAVI Cloud, la política del cliente lo habilita
   (`allow_local_cli`). Sin vinculación nadie lo gobierna y queda disponible.
"""

from __future__ import annotations

from app.infrastructure.config.settings import Settings


async def local_cli_allowed(settings: Settings) -> bool:
    if not settings.local_cli_enabled:
        return False
    # Import adentro: `cloud_link` importa modelos de otros módulos.
    from app.modules.cloud_link.infrastructure.composition import get_cloud_link_services

    try:
        services = get_cloud_link_services()
    except RuntimeError:
        return True
    state = await services.repository.get()
    if not state.has_credentials:
        return True
    return state.effective_policy.allow_local_cli
