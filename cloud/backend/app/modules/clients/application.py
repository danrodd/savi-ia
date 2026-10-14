from __future__ import annotations

from uuid import uuid4

from app.modules.clients.domain import (
    CLIENT_CODE_PATTERN,
    Client,
    ClientCodeAlreadyExists,
    ClientNotFound,
    ClientRepository,
    ClientStatus,
    InvalidClientCode,
    InvalidClientName,
)
from app.shared.clock import Clock


class CreateClientUseCase:
    def __init__(self, clients: ClientRepository, clock: Clock) -> None:
        self._clients = clients
        self._clock = clock

    async def execute(self, *, code: str, name: str, nit: str | None = None) -> Client:
        if not CLIENT_CODE_PATTERN.fullmatch(code):
            raise InvalidClientCode(
                "El código debe tener entre 2 y 32 caracteres de A-Z, 0-9 o _ (mayúsculas)."
            )
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 200:
            raise InvalidClientName("El nombre es obligatorio y admite hasta 200 caracteres.")
        if await self._clients.get_by_code(code) is not None:
            raise ClientCodeAlreadyExists(f"Ya existe un cliente con el código {code}.")
        now = self._clock()
        client = Client(
            id=uuid4(),
            code=code,
            name=clean_name,
            nit=nit.strip() if nit and nit.strip() else None,
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        await self._clients.add(client)
        return client


class ListClientsUseCase:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def execute(self) -> list[Client]:
        return await self._clients.list_all()


class GetClientByCodeUseCase:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    async def execute(self, code: str) -> Client:
        client = await self._clients.get_by_code(code)
        if client is None:
            raise ClientNotFound(f"No existe el cliente {code}.")
        return client
