"""Restablecimiento del segundo factor por un administrador de la instalación."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.modules.auth.application.requests import MfaResetRequest
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.admin import require_platform_admin
from app.modules.auth.infrastructure.http.dependencies import ResetMfaUseCaseDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/mfa", tags=["auth"])


class MfaResetResponse(BaseModel):
    # `False` = esa persona no tenía segundo factor (o el login no existe): no es un error.
    reset: bool


@router.post("/reset", response_model=MfaResetResponse)
async def reset_mfa(
    request: MfaResetRequest,
    use_case: ResetMfaUseCaseDep,
    admin: AuthenticatedUser = Depends(require_platform_admin),
) -> MfaResetResponse:
    """Borra el TOTP de un usuario y cierra sus sesiones: en el próximo ingreso configura uno
    nuevo. Para quien perdió el celular."""
    done = await use_case.execute(request.login)
    # Auditoría mínima en el log: quién restableció a quién, sin ningún secreto.
    logger.warning(
        "MFA restablecido por %s para %s (existía: %s)", admin.login, request.login, done
    )
    return MfaResetResponse(reset=done)
