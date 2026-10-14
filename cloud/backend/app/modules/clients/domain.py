from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.modules.clients.policies import AccessPolicy, AiPolicy
from app.modules.clients.subscription import Subscription
from app.shared.errors import DomainError

CLIENT_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,32}$")


class ClientStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class IdentityMode(StrEnum):
    """Cómo se identifica a las personas de un cliente en Cloud."""

    # Seudónimo (HMAC): Cloud cuenta usuarios sin saber quiénes son. Es el modo de los clientes.
    PSEUDONYM = "pseudonym"
    # Código de usuario del ERP. Solo para la organización interna (SEO Group): ahí
    # "5 SAVI funcionando" tiene que poder decir de quiénes son.
    NAMED = "named"


@dataclass(frozen=True)
class Client:
    id: UUID
    code: str
    name: str
    nit: str | None
    status: ClientStatus
    created_at: datetime
    updated_at: datetime
    identity_mode: IdentityMode = IdentityMode.PSEUDONYM
    # Las instalaciones de este cliente quedan solo con el chat (sin Administración).
    config_locked: bool = False
    # Las instalaciones locales pueden ofrecer el CLI de Claude con la cuenta de la persona.
    allow_local_cli: bool = False
    # Proveedores permitidos y topes de IA (M3). Vacía = sin límites.
    ai_policy: AiPolicy = field(default_factory=AiPolicy)
    # Bases que puede consultar cada persona (M4). Vacía = lo que permita el ERP.
    access_policy: AccessPolicy = field(default_factory=AccessPolicy)
    # Plan contratado y vigencia (M5-A). Vacía = sin plan cargado.
    subscription: Subscription = field(default_factory=Subscription)


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

    async def save(self, client: Client) -> None:
        """Persiste los campos mutables (nombre, NIT, estado)."""
        ...
