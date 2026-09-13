"""Endpoint del selector de base para el chat.

Separado de las rutas de administración: este lo usa cualquier usuario
autenticado, no solo un admin. Devuelve únicamente las bases donde el
usuario **tiene acceso** (D3) y solo `id`/`code`/`name` — nunca la
topología de conexión.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.erp_databases.application.responses import AvailableDatabaseResponse
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ListAvailableDatabasesUseCaseDep,
)

router = APIRouter(prefix="/erp-databases", tags=["erp-databases"])


@router.get("/available", response_model=list[AvailableDatabaseResponse])
async def list_available(
    use_case: ListAvailableDatabasesUseCaseDep,
    user: CurrentUserDep,
) -> list[AvailableDatabaseResponse]:
    """Bases activas donde el usuario autenticado puede consultar.

    El acceso se resuelve por `codigo` contra cada base (D3): una base
    donde el usuario no existe o está inactivo no aparece, aunque esté
    activa.
    """
    results = await use_case.execute(user.login)
    return [AvailableDatabaseResponse.from_dto(r) for r in results]
