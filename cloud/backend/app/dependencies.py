"""Dependencias HTTP compartidas: transacción, autenticación Bearer y límites de tasa."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.instances.application import AuthenticateInstanceUseCase
from app.modules.instances.domain import Instance, InstanceUnauthorized
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.shared.clock import Clock
from app.shared.http_errors import ApiError
from app.shared.rate_limit import SlidingWindowLimiter

REDEEM_LIMIT = 10  # intentos por IP...
REDEEM_WINDOW_SECONDS = 15 * 60  # ...cada 15 minutos
HEARTBEAT_LIMIT_PER_MINUTE = 60
INGEST_LIMIT_PER_MINUTE = 30
CONSOLE_AUTH_LIMIT = 30  # pasos de autenticación por IP...
CONSOLE_AUTH_WINDOW_SECONDS = 15 * 60  # ...cada 15 minutos


@dataclass(frozen=True)
class RateLimiters:
    redeem: SlidingWindowLimiter
    heartbeat: SlidingWindowLimiter
    ingest: SlidingWindowLimiter
    console_auth: SlidingWindowLimiter

    @classmethod
    def create(cls, clock: Clock) -> RateLimiters:
        def now() -> float:
            return clock().timestamp()

        return cls(
            redeem=SlidingWindowLimiter(REDEEM_LIMIT, REDEEM_WINDOW_SECONDS, now),
            heartbeat=SlidingWindowLimiter(HEARTBEAT_LIMIT_PER_MINUTE, 60, now),
            ingest=SlidingWindowLimiter(INGEST_LIMIT_PER_MINUTE, 60, now),
            console_auth=SlidingWindowLimiter(CONSOLE_AUTH_LIMIT, CONSOLE_AUTH_WINDOW_SECONDS, now),
        )


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


@asynccontextmanager
async def transaction(request: Request) -> AsyncGenerator[AsyncSession]:
    """Una transacción por request: confirma al salir bien y revierte ante cualquier error.

    Los endpoints la abren dentro del handler (no como dependencia con `yield`) para que el
    commit ocurra **antes** de responder: la instancia nunca recibe un 200 sin persistencia.
    """
    maker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with maker() as session, session.begin():
        yield session


def _enforce(limiter: SlidingWindowLimiter, key: str) -> None:
    retry_after = limiter.hit(key)
    if retry_after is not None:
        raise ApiError(
            429,
            "too_many_requests",
            "Demasiadas solicitudes; reintentá más tarde.",
            {"Retry-After": str(retry_after)},
        )


def _limiters(request: Request) -> RateLimiters:
    limiters: RateLimiters = request.app.state.limiters
    return limiters


async def limit_redeem(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    _enforce(_limiters(request).redeem, ip)


async def authenticated_instance(request: Request) -> Instance:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise InstanceUnauthorized("Falta el secreto de instancia (Authorization: Bearer).")
    async with transaction(request) as session:
        return await AuthenticateInstanceUseCase(
            SqlAlchemyInstanceRepository(session), get_clock(request)
        ).execute(token.strip())


async def heartbeat_instance(
    request: Request, instance: Instance = Depends(authenticated_instance)
) -> Instance:
    _enforce(_limiters(request).heartbeat, str(instance.id))
    return instance


async def ingest_instance(
    request: Request, instance: Instance = Depends(authenticated_instance)
) -> Instance:
    _enforce(_limiters(request).ingest, str(instance.id))
    return instance
