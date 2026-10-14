"""API de la consola (`/console/api`, §3 de la Fase 3).

Cada ruta declara `RequirePermission`; un test recorre el router y falla si falta alguna.
El frontend oculta lo que el backend igual rechaza.

Una carpeta por área: `clients`, `billing`, `instances`, `tokens`, `staff` y `audit`; los
modelos están en `schemas` y lo compartido en `common`.
"""

from fastapi import APIRouter

from app.modules.console.presentation import audit, billing, clients, instances, staff, tokens

router = APIRouter(prefix="/console/api", tags=["console"])
router.include_router(clients.router)
router.include_router(billing.router)
router.include_router(instances.router)
router.include_router(tokens.router)
router.include_router(staff.router)
router.include_router(audit.router)

__all__ = ["router"]
