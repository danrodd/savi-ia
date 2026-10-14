"""Repositorios SQLAlchemy y flujo completo de vinculación sobre SQLite (portable)."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import create_engine, create_sessionmaker
from app.modules.clients.application import CreateClientUseCase
from app.modules.clients.domain import ClientCodeAlreadyExists
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.enrollments.application import (
    CreateEnrollmentTokenUseCase,
    RedeemEnrollmentTokenUseCase,
    RevokeEnrollmentTokenUseCase,
)
from app.modules.enrollments.domain import EnrollmentTokenInvalid, InstanceInfo
from app.modules.enrollments.infrastructure import (
    EnrollmentTokenModel,
    SqlAlchemyEnrollmentTokenRepository,
)
from app.modules.instances.application import ListInstancesUseCase
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.shared.clock import utc_now
from app.shared.tokens import hash_secret

INFO = InstanceInfo(
    name="SRV-FARMX",
    deployment_mode="server",
    version=None,
    commit=None,
    os="Ubuntu",
    agent_db_engine="postgresql",
    fingerprint="fp",
)


async def test_full_flow_persists_only_hashes(sqlite_url: str) -> None:
    engine = create_engine(sqlite_url)
    maker = create_sessionmaker(engine)
    try:
        async with maker() as s, s.begin():
            clients = SqlAlchemyClientRepository(s)
            tokens = SqlAlchemyEnrollmentTokenRepository(s)
            await CreateClientUseCase(clients, utc_now).execute(code="FARMX", name="Farmacias X")
            created = await CreateEnrollmentTokenUseCase(clients, tokens, utc_now).execute(
                client_code="FARMX"
            )
        plaintext = created.plaintext

        async with maker() as s, s.begin():
            raw = (await s.execute(select(EnrollmentTokenModel))).scalar_one()
            assert bytes(raw.token_hash) == hash_secret(plaintext)
            assert plaintext.encode() not in bytes(raw.token_hash)

        async with maker() as s, s.begin():
            result = await RedeemEnrollmentTokenUseCase(
                SqlAlchemyClientRepository(s),
                SqlAlchemyEnrollmentTokenRepository(s),
                SqlAlchemyInstanceRepository(s),
                utc_now,
            ).execute(token=plaintext, info=INFO)

        async with maker() as s, s.begin():
            with pytest.raises(EnrollmentTokenInvalid):
                await RedeemEnrollmentTokenUseCase(
                    SqlAlchemyClientRepository(s),
                    SqlAlchemyEnrollmentTokenRepository(s),
                    SqlAlchemyInstanceRepository(s),
                    utc_now,
                ).execute(token=plaintext, info=INFO)
            listed = await ListInstancesUseCase(
                SqlAlchemyClientRepository(s), SqlAlchemyInstanceRepository(s)
            ).execute("FARMX")
            assert [i.id for i in listed] == [result.instance.id]
            assert listed[0].secret_hash == hash_secret(result.instance_secret)
            assert listed[0].enrolled_at.tzinfo is not None
    finally:
        await engine.dispose()


async def test_unique_code_enforced_by_database(sqlite_url: str) -> None:
    engine = create_engine(sqlite_url)
    maker = create_sessionmaker(engine)
    try:
        async with maker() as s, s.begin():
            repo = SqlAlchemyClientRepository(s)
            first = await CreateClientUseCase(repo, utc_now).execute(code="DUP", name="Uno")
            # Salta la verificación del caso de uso: debe fallar la restricción de la BD.
            with pytest.raises(ClientCodeAlreadyExists):
                await repo.add(replace(first, id=uuid4()))
            # La transacción externa sigue utilizable (savepoint).
            assert await repo.get_by_code("DUP") is not None
    finally:
        await engine.dispose()


async def test_revoke_persists(sqlite_url: str) -> None:
    engine = create_engine(sqlite_url)
    maker = create_sessionmaker(engine)
    try:
        async with maker() as s, s.begin():
            clients = SqlAlchemyClientRepository(s)
            tokens = SqlAlchemyEnrollmentTokenRepository(s)
            await CreateClientUseCase(clients, utc_now).execute(code="REV", name="Rev")
            created = await CreateEnrollmentTokenUseCase(clients, tokens, utc_now).execute(
                client_code="REV"
            )
            await RevokeEnrollmentTokenUseCase(tokens, utc_now).execute(created.token.id)
        async with maker() as s2:
            assert isinstance(s2, AsyncSession)
            stored = await SqlAlchemyEnrollmentTokenRepository(s2).get_by_id(created.token.id)
            assert stored is not None and stored.revoked_at is not None
    finally:
        await engine.dispose()
