"""Siembra la base default desde el `.env` al arrancar.

El instalador sigue configurando **una** BD del ERP en `backend/.env`.
Esa conexión pasa a ser una fila más de `erp_databases`, marcada como
default. A partir de ahí el `.env` deja de ser la fuente de verdad en
runtime: las demás bases se administran desde la aplicación.

Idempotente por "la tabla está vacía", no por `(host, port, database)`:
si el administrador eliminó esa fila a propósito, el arranque no debe
resucitarla.
"""
from __future__ import annotations

import logging

from app.infrastructure.config.settings import Settings
from app.modules.erp_databases.domain.entities import ErpDatabase
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository
from app.modules.erp_databases.domain.value_objects import (
    InvalidDatabaseCodeError,
    normalize_code,
)

logger = logging.getLogger(__name__)

SEED_CODE = "PRINCIPAL"
SEED_NAME = "Principal"


def has_seed_config(settings: Settings) -> bool:
    return bool(settings.erp_db_host and settings.erp_db_name)


def erp_database_from_settings(settings: Settings) -> ErpDatabase:
    """Arma la entidad a partir del bloque `ERP_DB_*` del `.env`.

    Se usa para sembrar y también para el diagnóstico previo al arranque
    del launcher, que necesita la URL antes de que exista el registry.
    Una sola definición para que las dos no se desincronicen.
    """
    try:
        code = normalize_code(settings.erp_db_name)
    except InvalidDatabaseCodeError:
        # El nombre de la BD puede no ser un código válido (muy largo, con
        # puntos). Se cae a un código fijo en vez de fallar: es una
        # etiqueta que el administrador puede cambiar después.
        code = SEED_CODE

    return ErpDatabase(
        code=code,
        name=settings.erp_db_name or SEED_NAME,
        host=settings.erp_db_host,
        port=settings.erp_db_port,
        database=settings.erp_db_name,
        username=settings.erp_db_user,
        password=settings.erp_db_password,
        statement_timeout_ms=settings.erp_db_statement_timeout_ms,
        is_default=True,
        is_active=True,
        seed_revision=settings.erp_seed_revision.strip() or None,
    )


async def _resync_default_database(
    repository: ErpDatabaseRepository,
    settings: Settings,
) -> None:
    """Aplica un `.env` reconfigurado a la base default ya sembrada.

    "Volver a configurar" del instalador escribe un `ERP_SEED_REVISION`
    nuevo. Si difiere del guardado en la fila, el administrador pidió
    cambiar el ERP desde el instalador y se actualiza la conexión. Con la
    misma revisión (o sin revisión, como en un `.env` anterior) no se toca
    nada: hacerlo en cada arranque pisaría lo que el administrador editó
    desde la aplicación.

    Solo se actualizan los campos de conexión; el nombre y el código los
    puede haber cambiado el administrador (el código además es el sufijo
    del login de los usuarios).
    """
    revision = settings.erp_seed_revision.strip()
    if not revision or not has_seed_config(settings):
        return

    default = await repository.get_default()
    if default is None or default.seed_revision == revision:
        return

    seed = erp_database_from_settings(settings)
    default.host = seed.host
    default.port = seed.port
    default.database = seed.database
    default.username = seed.username
    default.password = seed.password
    default.seed_revision = revision
    await repository.save(default)
    logger.info(
        "Base default '%s' actualizada desde el .env (revisión %s): host=%s, base=%s.",
        default.name,
        revision,
        default.host,
        default.database,
    )


async def seed_default_database(
    repository: ErpDatabaseRepository,
    settings: Settings,
) -> None:
    if await repository.count() > 0:
        await _resync_default_database(repository, settings)
        return

    if not has_seed_config(settings):
        # Sin ERP en el `.env` no hay nada que sembrar. No es un error:
        # un despliegue nuevo puede registrar su primera base desde la
        # sección de administración.
        logger.info(
            "No hay bases del ERP registradas y ERP_DB_* está vacío: "
            "registrá la primera desde la sección de administración."
        )
        return

    database = erp_database_from_settings(settings)
    await repository.save(database)
    logger.info(
        "Base del ERP sembrada desde .env como default: '%s' (código %s). "
        "La contraseña quedó cifrada en la BD del agente; conviene vaciar "
        "ERP_DB_PASSWORD del .env.",
        database.name,
        database.code,
    )
