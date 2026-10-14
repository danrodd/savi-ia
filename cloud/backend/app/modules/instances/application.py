from __future__ import annotations

from app.modules.clients.domain import ClientNotFound, ClientRepository
from app.modules.instances.domain import Instance, InstanceRepository


class ListInstancesUseCase:
    def __init__(self, clients: ClientRepository, instances: InstanceRepository) -> None:
        self._clients = clients
        self._instances = instances

    async def execute(self, client_code: str) -> list[Instance]:
        client = await self._clients.get_by_code(client_code)
        if client is None:
            raise ClientNotFound(f"No existe el cliente {client_code}.")
        return await self._instances.list_by_client(client.id)
