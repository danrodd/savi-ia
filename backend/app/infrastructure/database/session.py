from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.pool import get_agent_engine


def get_agent_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Sessionmaker bound al engine del agente, sin lifecycle del request.

    Útil para escrituras que deben sobrevivir a la cancelación del request
    (ej. persistir la respuesta parcial del asistente cuando el cliente
    cortó el stream): el caller despacha `create_task(writer.write(...))`
    y la sesión nueva no depende de la sesión que FastAPI cierra al
    terminar el request.
    """
    return async_sessionmaker(
        bind=get_agent_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


async def get_agent_session() -> AsyncIterator[AsyncSession]:
    factory = get_agent_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


AgentSessionDep = Annotated[AsyncSession, Depends(get_agent_session)]

# `get_erp_session` / `ErpSessionDep` se eliminaron: con varias bases de
# clientes no hay una sesión "del ERP" resoluble sin saber cuál. Los
# consumidores piden el engine por id vía `ErpConnectionProvider`.
