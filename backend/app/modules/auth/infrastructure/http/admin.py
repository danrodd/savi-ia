"""Gates de administración de SAVI (D9).

Hay **dos** roles distintos, y confundirlos fue el hallazgo A3 de la revisión:

- **Administrador de la instalación** (`require_platform_admin`): conexiones a
  las bases de clientes, keys de los proveedores de IA, consumo global.
- **Administrador de empresa** (`require_company_admin`): los documentos y el
  consumo de SU empresa.

Antes había uno solo, `is_savi_admin = user.is_admin or login en
SAVI_ADMIN_LOGINS`, donde `user.is_admin` es el flag `administrador` **de la
base contra la que el usuario inició sesión**. En una instalación con varias
empresas, el administrador del ERP del cliente A podía ver y editar las
conexiones del cliente B, e incluso **exportarlas con sus contraseñas**.

**Por qué el escape por lista:** un agente de soporte puede no ser
`administrador` en ninguna base del ERP y aun así ser el dueño de su propia
instalación de escritorio. Exigirle un flag del ERP lo dejaría afuera de su
propia herramienta.

**Compatibilidad deliberada:** con **una sola base registrada** no hay nada que
aislar, así que el administrador de esa base sigue siendo administrador de la
instalación. Es el caso de la app de escritorio, que es el despliegue actual:
la distinción aparece recién cuando hay más de una empresa.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.infrastructure.config import Settings, get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import CurrentUserDep
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.shared.exceptions import ForbiddenError


def is_savi_admin(user: AuthenticatedUser, settings: Settings) -> bool:
    """Administrador de SU empresa. No alcanza para tocar otras."""
    return user.is_admin or user.login.strip().upper() in settings.savi_admin_logins_set


def _is_listed_admin(user: AuthenticatedUser, settings: Settings) -> bool:
    return user.login.strip().upper() in settings.savi_admin_logins_set


def _erp_database_repository() -> ErpDatabaseRepository:
    # Import adentro: `erp_databases` importa de `auth`.
    from app.infrastructure.config import get_settings as _settings
    from app.modules.erp_databases.infrastructure.http.dependencies import (
        get_erp_database_repository,
    )

    return get_erp_database_repository(_settings())


async def is_platform_admin(user: AuthenticatedUser, settings: Settings) -> bool:
    """¿Administra la instalación entera? Versión que **no** levanta.

    La usan las rutas que no bloquean, sino que acotan los datos: un
    administrador de empresa ve sus documentos, uno de instalación ve todos.
    """
    if _is_listed_admin(user, settings):
        return True
    if not user.is_admin:
        return False

    repository = _erp_database_repository()
    databases = await repository.list_all(include_inactive=True)
    if len(databases) <= 1:
        # Instalación de una sola empresa: no hay aislamiento que romper.
        return True

    default = await repository.get_default()
    return default is not None and default.id == user.erp_database_id


async def require_platform_admin(
    user: CurrentUserDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """Administra la INSTALACIÓN: bases, proveedores de IA, consumo global.

    Ser administrador del ERP de una base **no** alcanza cuando hay varias:
    ahí el rol lo dan `SAVI_ADMIN_LOGINS` o ser administrador de la base por
    defecto.
    """
    if not await is_platform_admin(user, settings):
        raise ForbiddenError(
            "Administrar las bases de datos, los proveedores de IA y el consumo "
            "global de la instalación requiere un administrador de la instalación."
        )
    return user


def require_company_admin(
    user: CurrentUserDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    """Administra SU empresa: documentos y consumo de su base."""
    if not is_savi_admin(user, settings):
        raise ForbiddenError("Se requiere rol administrador de la empresa.")
    return user


# Alias histórico: el gate de empresa es el que aplica a la mayoría de las
# rutas `/admin`. Las de instalación usan `PlatformAdminDep`.
SaviAdminDep = Annotated[AuthenticatedUser, Depends(require_company_admin)]
PlatformAdminDep = Annotated[AuthenticatedUser, Depends(require_platform_admin)]
CompanyAdminDep = Annotated[AuthenticatedUser, Depends(require_company_admin)]
