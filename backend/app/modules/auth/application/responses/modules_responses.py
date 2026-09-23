"""Responses del subsistema de módulos/permisos.

- BootstrapResponse → respuesta de /auth/me/bootstrap.
- ModulesVersionResponse → respuesta del polling de version.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.auth.application.responses.auth_responses import (
    AuthenticatedUserResponse,
    SessionDatabaseResponse,
)
from app.modules.auth.application.use_cases.resolve_modules_for_database import (
    DatabaseAccess,
)
from app.modules.auth.application.use_cases.resolve_user_modules import (
    UserModulesResolution,
)
from app.modules.auth.domain.entities import AuthenticatedUser


class BootstrapResponse(BaseModel):
    """Snapshot completo de identidad + autorización del usuario actual.

    Lo consume el frontend al login y tras detectar cambios de versión.
    No incluye tokens — solo se llama con un access válido (Bearer).
    """

    user: AuthenticatedUserResponse
    modules: list[str]
    version: str

    @classmethod
    def from_domain(
        cls,
        user: AuthenticatedUser,
        resolution: UserModulesResolution,
    ) -> BootstrapResponse:
        return cls(
            user=AuthenticatedUserResponse.from_domain(user),
            modules=sorted(m.value for m in resolution.modules),
            version=resolution.version,
        )

    @classmethod
    def from_database_access(
        cls,
        user: AuthenticatedUser,
        access: DatabaseAccess,
        erp_database: SessionDatabaseResponse | None = None,
    ) -> BootstrapResponse:
        """Desde el acceso resuelto contra LA base del usuario.

        Antes se usaba `from_domain` con un resolver que consultaba la base
        por defecto: un usuario de otra base recibía los módulos del usuario
        con el mismo `idUsuario` allá."""
        return cls(
            user=AuthenticatedUserResponse.from_domain(user, erp_database),
            modules=sorted(m.value for m in access.modules),
            version=access.version,
        )


class ModulesVersionResponse(BaseModel):
    """Hash de versión actual. El cliente lo compara contra el cacheado."""

    version: str

    @classmethod
    def from_domain(cls, resolution: UserModulesResolution) -> ModulesVersionResponse:
        return cls(version=resolution.version)

    @classmethod
    def from_database_access(cls, access: DatabaseAccess) -> ModulesVersionResponse:
        return cls(version=access.version)
