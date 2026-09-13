"""Backfill de las filas anteriores al multi-BD.

Corre al arrancar, **después** del seed: hasta que la base default
existe no hay a qué apuntar las filas viejas.

No vive en la migración Alembic porque la migración no puede saber cuál
es la base default sin leer el `.env`, y darle esa responsabilidad
acoplaría el historial de esquema a la configuración.

Solo toca filas con `erp_database_id IS NULL`. Es idempotente y, una vez
que no queda ninguna, cuesta un `UPDATE` que no matchea nada.
"""
from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
)
from app.modules.free_query.infrastructure.models import AuditQueryModel

logger = logging.getLogger(__name__)


async def backfill_legacy_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
    default_database_id: UUID,
) -> None:
    """Asigna la base default a las conversaciones y auditorías sin base.

    Es correcto porque antes del multi-BD **solo existía una** base del
    ERP: toda fila anterior se consultó necesariamente contra la que
    ahora quedó como default, y su dueño solo pudo haber iniciado sesión
    en esa misma base.

    Las conversaciones reciben tanto `erp_database_id` (la consultada)
    como `owner_erp_database_id` (la identidad del dueño) — antes de
    D10 eran siempre la misma base, así que backfillear las dos con el
    mismo valor no es una aproximación.

    Los `refresh_token` NO se backfillean a propósito: un token viejo se
    rechaza y el usuario vuelve a iniciar sesión una vez. Rellenarlos
    sería asumir que su dueño pertenece a la default, que es justamente
    la suposición que este cambio elimina — y a diferencia de una
    conversación, un token mal atribuido da acceso.
    """
    async with sessionmaker() as session:
        conversations = cast(
            CursorResult[Any],
            await session.execute(
                update(ConversationModel)
                .where(ConversationModel.erp_database_id.is_(None))
                .values(
                    erp_database_id=default_database_id,
                    owner_erp_database_id=default_database_id,
                )
            ),
        )
        audits = cast(
            CursorResult[Any],
            await session.execute(
                update(AuditQueryModel)
                .where(AuditQueryModel.erp_database_id.is_(None))
                .values(erp_database_id=default_database_id)
            ),
        )
        await session.commit()

    if conversations.rowcount or audits.rowcount:
        logger.info(
            "Backfill multi-BD: %d conversaciones y %d auditorías asignadas "
            "a la base default.",
            conversations.rowcount,
            audits.rowcount,
        )
