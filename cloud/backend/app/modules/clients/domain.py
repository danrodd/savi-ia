from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.shared.errors import DomainError

CLIENT_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,32}$")


class ClientStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass(frozen=True)
class Client:
    id: UUID
    code: str
    name: str
    nit: str | None
    status: ClientStatus
    created_at: datetime
    updated_at: datetime


class InvalidClientCode(DomainError):
    code = "invalid_client_code"


class InvalidClientName(DomainError):
    code = "invalid_client_name"


class ClientCodeAlreadyExists(DomainError):
    code = "client_code_already_exists"


class ClientNotFound(DomainError):
    code = "client_not_found"


class ClientSuspended(DomainError):
    code = "client_suspended"


class ClientRepository(Protocol):
    async def add(self, client: Client) -> None:
        """Persiste. Levanta `ClientCodeAlreadyExists` si el código ya existe."""
        ...

    async def get_by_id(self, client_id: UUID) -> Client | None: ...

    async def get_by_code(self, code: str) -> Client | None: ...

    async def list_all(self) -> list[Client]: ...
