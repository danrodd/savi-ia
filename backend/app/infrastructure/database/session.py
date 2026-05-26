from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.pool import get_agent_engine, get_erp_engine


async def get_agent_session() -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(
        bind=get_agent_engine(),
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_erp_session() -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(
        bind=get_erp_engine(),
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


AgentSessionDep = Annotated[AsyncSession, Depends(get_agent_session)]
ErpSessionDep = Annotated[AsyncSession, Depends(get_erp_session)]
