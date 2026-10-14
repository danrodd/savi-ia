"""Repositorios en memoria para probar los casos de uso sin base de datos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.clients.domain import Client, ClientCodeAlreadyExists
from app.modules.enrollments.domain import EnrollmentToken
from app.modules.instances.domain import Instance


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


class FakeClientRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Client] = {}

    async def add(self, client: Client) -> None:
        if any(c.code == client.code for c in self.items.values()):
            raise ClientCodeAlreadyExists(client.code)
        self.items[client.id] = client

    async def get_by_id(self, client_id: UUID) -> Client | None:
        return self.items.get(client_id)

    async def get_by_code(self, code: str) -> Client | None:
        return next((c for c in self.items.values() if c.code == code), None)

    async def list_all(self) -> list[Client]:
        return sorted(self.items.values(), key=lambda c: c.code)


class FakeEnrollmentTokenRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, EnrollmentToken] = {}

    async def add(self, token: EnrollmentToken) -> None:
        self.items[token.id] = token

    async def get_by_id(self, token_id: UUID) -> EnrollmentToken | None:
        return self.items.get(token_id)

    async def get_by_hash_for_update(self, token_hash: bytes) -> EnrollmentToken | None:
        return next((t for t in self.items.values() if t.token_hash == token_hash), None)

    async def list_by_client(self, client_id: UUID) -> list[EnrollmentToken]:
        return [t for t in self.items.values() if t.client_id == client_id]

    async def save(self, token: EnrollmentToken) -> None:
        self.items[token.id] = token


class FakeInstanceRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Instance] = {}

    async def add(self, instance: Instance) -> None:
        self.items[instance.id] = instance

    async def get_by_id(self, instance_id: UUID) -> Instance | None:
        return self.items.get(instance_id)

    async def get_for_update(self, instance_id: UUID) -> Instance | None:
        return self.items.get(instance_id)

    async def get_by_secret_hash(self, secret_hash: bytes) -> Instance | None:
        return next(
            (
                i
                for i in self.items.values()
                if i.secret_hash == secret_hash or i.previous_secret_hash == secret_hash
            ),
            None,
        )

    async def list_by_client(self, client_id: UUID) -> list[Instance]:
        return [i for i in self.items.values() if i.client_id == client_id]

    async def save(self, instance: Instance) -> None:
        self.items[instance.id] = instance
