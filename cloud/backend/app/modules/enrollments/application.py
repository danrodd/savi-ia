"""Casos de uso de vinculación.

No abren ni cierran transacciones: el llamador (CLI o endpoint HTTP) envuelve cada caso de
uso en una transacción. Canjear el token y crear la instancia van juntos en esa transacción
(§3.1), con el token bloqueado por `get_by_hash_for_update`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID, uuid4

from app.modules.clients.domain import (
    Client,
    ClientNotFound,
    ClientRepository,
    ClientStatus,
    ClientSuspended,
)
from app.modules.enrollments.domain import (
    EnrollmentToken,
    EnrollmentTokenAlreadyUsed,
    EnrollmentTokenInvalid,
    EnrollmentTokenNotFound,
    EnrollmentTokenRepository,
    InstanceInfo,
    InvalidExpiration,
)
from app.modules.instances.domain import Instance, InstanceRepository, InstanceStatus
from app.shared.clock import Clock
from app.shared.tokens import (
    ENROLLMENT_TOKEN_PREFIX,
    INSTANCE_SECRET_PREFIX,
    generate_secret,
    hash_secret,
)

MAX_EXPIRATION_HOURS = 24 * 365


@dataclass(frozen=True)
class CreatedEnrollmentToken:
    token: EnrollmentToken
    plaintext: str  # única vez que existe: el llamador lo muestra y lo descarta


@dataclass(frozen=True)
class RedeemResult:
    instance: Instance
    client: Client
    instance_secret: str  # texto plano, solo en esta respuesta


class CreateEnrollmentTokenUseCase:
    def __init__(
        self,
        clients: ClientRepository,
        tokens: EnrollmentTokenRepository,
        clock: Clock,
        *,
        default_expires_hours: int = 72,
    ) -> None:
        self._clients = clients
        self._tokens = tokens
        self._clock = clock
        self._default_hours = default_expires_hours

    async def execute(
        self,
        *,
        client_code: str,
        expires_hours: int | None = None,
        created_by: str = "cloud-admin",
    ) -> CreatedEnrollmentToken:
        hours = self._default_hours if expires_hours is None else expires_hours
        if hours < 1 or hours > MAX_EXPIRATION_HOURS:
            raise InvalidExpiration(
                f"La vigencia debe estar entre 1 y {MAX_EXPIRATION_HOURS} horas."
            )
        client = await self._clients.get_by_code(client_code)
        if client is None:
            raise ClientNotFound(f"No existe el cliente {client_code}.")
        if client.status is not ClientStatus.ACTIVE:
            raise ClientSuspended(f"El cliente {client_code} está suspendido.")
        now = self._clock()
        plaintext = generate_secret(ENROLLMENT_TOKEN_PREFIX)
        token = EnrollmentToken(
            id=uuid4(),
            client_id=client.id,
            token_hash=hash_secret(plaintext),
            expires_at=now + timedelta(hours=hours),
            created_at=now,
            created_by=created_by,
        )
        await self._tokens.add(token)
        return CreatedEnrollmentToken(token=token, plaintext=plaintext)


class ListEnrollmentTokensUseCase:
    def __init__(self, clients: ClientRepository, tokens: EnrollmentTokenRepository) -> None:
        self._clients = clients
        self._tokens = tokens

    async def execute(self, client_code: str) -> list[EnrollmentToken]:
        client = await self._clients.get_by_code(client_code)
        if client is None:
            raise ClientNotFound(f"No existe el cliente {client_code}.")
        return await self._tokens.list_by_client(client.id)


class RevokeEnrollmentTokenUseCase:
    def __init__(self, tokens: EnrollmentTokenRepository, clock: Clock) -> None:
        self._tokens = tokens
        self._clock = clock

    async def execute(self, token_id: UUID) -> EnrollmentToken:
        token = await self._tokens.get_by_id(token_id)
        if token is None:
            raise EnrollmentTokenNotFound(f"No existe el token {token_id}.")
        if token.used_at is not None:
            raise EnrollmentTokenAlreadyUsed("El token ya fue canjeado; no se puede revocar.")
        if token.revoked_at is not None:
            return token  # idempotente
        revoked = replace(token, revoked_at=self._clock())
        await self._tokens.save(revoked)
        return revoked


class RedeemEnrollmentTokenUseCase:
    def __init__(
        self,
        clients: ClientRepository,
        tokens: EnrollmentTokenRepository,
        instances: InstanceRepository,
        clock: Clock,
    ) -> None:
        self._clients = clients
        self._tokens = tokens
        self._instances = instances
        self._clock = clock

    async def execute(self, *, token: str, info: InstanceInfo) -> RedeemResult:
        now = self._clock()
        found = await self._tokens.get_by_hash_for_update(hash_secret(token))
        if found is None or not found.is_redeemable(now):
            raise EnrollmentTokenInvalid("Token de vinculación inválido.")
        client = await self._clients.get_by_id(found.client_id)
        if client is None:  # FK lo impide; se trata como token inválido
            raise EnrollmentTokenInvalid("Token de vinculación inválido.")
        if client.status is not ClientStatus.ACTIVE:
            raise ClientSuspended("El cliente está suspendido.")

        secret = generate_secret(INSTANCE_SECRET_PREFIX)
        instance = Instance(
            id=uuid4(),
            client_id=client.id,
            name=info.name,
            deployment_mode=info.deployment_mode,
            os=info.os,
            agent_db_engine=info.agent_db_engine,
            version=info.version,
            commit=info.commit,
            status=InstanceStatus.ACTIVE,
            status_reason=None,
            secret_hash=hash_secret(secret),
            fingerprint=info.fingerprint,
            enrolled_at=now,
            created_at=now,
            updated_at=now,
        )
        await self._instances.add(instance)
        await self._tokens.save(replace(found, used_at=now, used_by_instance_id=instance.id))
        return RedeemResult(instance=instance, client=client, instance_secret=secret)
