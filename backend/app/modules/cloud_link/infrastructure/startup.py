"""Vinculación automática al arrancar (§6.2).

El instalador escribe `SAVI_CLOUD_ENROLLMENT_TOKEN` en el `.env`. Si hay token
y la instalación no está vinculada, se canjea **una sola vez** por arranque:
si falla (token vencido, sin red) queda `last_error_code` en Administración y
no se reintenta en bucle. Si sale bien, se vacía la variable del `.env`.
"""

import logging
from pathlib import Path

from app.modules.cloud_link.domain.exceptions import CloudApiError
from app.modules.cloud_link.domain.value_objects import HistoryMode, LinkStatus
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.cloud_link.infrastructure.env_file import clear_env_variable
from app.shared.exceptions.base import DomainError

logger = logging.getLogger(__name__)

TOKEN_ENV_KEY = "SAVI_CLOUD_ENROLLMENT_TOKEN"


async def link_from_settings(
    services: CloudLinkServices, *, env_path: Path | None = None
) -> LinkStatus | None:
    """Intenta la vinculación automática. Devuelve el estado resultante, o
    `None` si no había nada que hacer."""
    token = services.settings.savi_cloud_enrollment_token.strip()
    url = services.settings.savi_cloud_url.strip()
    if not token or not url:
        return None

    env = env_path or Path(".env")
    state = await services.repository.get()
    if state.status != LinkStatus.UNLINKED:
        # Ya vinculada (p. ej. el token quedó en el .env tras un arranque que
        # no pudo limpiarlo): no hay nada que canjear.
        clear_env_variable(env, TOKEN_ENV_KEY)
        return state.status

    try:
        linked = await services.link.execute(cloud_url=url, token=token, history=HistoryMode.ALL)
    except CloudApiError as error:
        logger.warning(
            "No se pudo vincular con SAVI Cloud al arrancar (%s). Se puede reintentar "
            "desde Administración.",
            error.error_code,
        )
        return None
    except DomainError as error:
        logger.warning("No se pudo vincular con SAVI Cloud al arrancar: %s", error)
        return None

    clear_env_variable(env, TOKEN_ENV_KEY)
    logger.info("Instalación vinculada con SAVI Cloud (cliente %s).", linked.client_code)
    return linked.status
