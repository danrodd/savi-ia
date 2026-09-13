"""Gate de administración de SAVI (D9).

Distinto de `is_admin` a secas: además del flag del ERP, acepta los
códigos listados en `SAVI_ADMIN_LOGINS`.

**Por qué hace falta el escape:** un agente de soporte puede no ser
`administrador` en ninguna base del ERP y aun así ser el dueño de su
propia instalación de escritorio. Exigirle un flag del ERP lo dejaría
afuera de su propia herramienta.

**Alcance deliberadamente limitado:** esto habilita la sección de
administración de SAVI y nada más. No toca `ResolveUserModulesUseCase`,
no otorga módulos del ERP y no cambia qué datos puede consultar.
Administrar conexiones y tener acceso a datos son cosas distintas.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import CurrentUserDep
from app.shared.exceptions import ForbiddenError


def is_savi_admin(user: AuthenticatedUser, settings: Settings) -> bool:
    return user.is_admin or user.login.strip().upper() in settings.savi_admin_logins_set


def require_savi_admin(
    user: CurrentUserDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    if not is_savi_admin(user, settings):
        raise ForbiddenError(
            "Se requiere rol administrador para administrar las bases de datos."
        )
    return user


SaviAdminDep = Annotated[AuthenticatedUser, Depends(require_savi_admin)]
