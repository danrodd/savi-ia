"""Endpoints de administración de las bases del ERP.

Todos bajo `/admin/erp-databases` y protegidos por `SaviAdminDep` (D9).

La contraseña entra por el body y nunca sale por ninguna respuesta.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.auth.infrastructure.http.admin import SaviAdminDep
from app.modules.erp_databases.application.requests import SaveErpDatabaseRequest
from app.modules.erp_databases.application.responses import (
    ConnectionTestResponse,
    ErpDatabaseResponse,
)
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ManageErpDatabasesUseCaseDep,
)

router = APIRouter(prefix="/admin/erp-databases", tags=["erp-databases"])


@router.get("", response_model=list[ErpDatabaseResponse])
async def list_databases(
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
    include_inactive: bool = Query(
        default=False,
        description="Incluir las desactivadas. Las eliminadas nunca se listan.",
    ),
) -> list[ErpDatabaseResponse]:
    results = await use_case.list(include_inactive=include_inactive)
    return [ErpDatabaseResponse.from_dto(r) for r in results]


@router.post(
    "",
    response_model=ErpDatabaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_database(
    request: SaveErpDatabaseRequest,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> ErpDatabaseResponse:
    """Registra una base nueva.

    El test de conexión corre antes de persistir: si falla, devuelve 422
    y no se guarda nada (D5).
    """
    return ErpDatabaseResponse.from_dto(await use_case.create(request.to_dto()))


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    request: SaveErpDatabaseRequest,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
    database_id: UUID | None = Query(
        default=None,
        description=(
            "Para re-testear una base ya guardada reutilizando su contraseña "
            "almacenada, sin tener que reenviarla."
        ),
    ),
) -> ConnectionTestResponse:
    """El botón "probar conexión" del formulario. No persiste nada.

    Devuelve 200 aunque la conexión falle: el resultado va en `ok`. Un
    dato de conexión equivocado es entrada mal cargada, no un error del
    servidor.
    """
    result = await use_case.test_connection(request.to_dto(), database_id=database_id)
    return ConnectionTestResponse.from_result(result)


@router.get("/{database_id}", response_model=ErpDatabaseResponse)
async def get_database(
    database_id: UUID,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> ErpDatabaseResponse:
    return ErpDatabaseResponse.from_dto(await use_case.get(database_id))


@router.patch("/{database_id}", response_model=ErpDatabaseResponse)
async def update_database(
    database_id: UUID,
    request: SaveErpDatabaseRequest,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> ErpDatabaseResponse:
    """Edita una base. Contraseña vacía = conservar la guardada.

    Al guardar se invalida el engine: sin eso, cambiar la contraseña no
    tendría efecto hasta reiniciar el proceso.
    """
    return ErpDatabaseResponse.from_dto(
        await use_case.update(database_id, request.to_dto())
    )


@router.post("/{database_id}/set-default", response_model=ErpDatabaseResponse)
async def set_default(
    database_id: UUID,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> ErpDatabaseResponse:
    return ErpDatabaseResponse.from_dto(await use_case.set_default(database_id))


@router.post("/{database_id}/activate", response_model=ErpDatabaseResponse)
async def activate(
    database_id: UUID,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> ErpDatabaseResponse:
    return ErpDatabaseResponse.from_dto(await use_case.activate(database_id))


@router.post("/{database_id}/deactivate", response_model=ErpDatabaseResponse)
async def deactivate(
    database_id: UUID,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> ErpDatabaseResponse:
    """Desactiva una base. 422 si es la predeterminada.

    Los chats contra ella quedan en solo lectura: el historial se sigue
    leyendo, pero no se pueden enviar turnos nuevos.
    """
    return ErpDatabaseResponse.from_dto(await use_case.deactivate(database_id))


@router.delete("/{database_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_database(
    database_id: UUID,
    use_case: ManageErpDatabasesUseCaseDep,
    _admin: SaviAdminDep,
) -> None:
    """Baja lógica idempotente. 422 si es la predeterminada.

    Nunca borra físicamente: `conversations.erp_database_id` es una FK y
    el historial tiene que seguir siendo legible.
    """
    await use_case.soft_delete(database_id)
