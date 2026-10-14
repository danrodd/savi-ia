"""Casos de uso de instancias. No abren transacciones: lo hace el llamador (HTTP o CLI)."""

from __future__ import annotations

import hmac
from dataclasses import replace
from datetime import timedelta
from typing import Literal
from uuid import UUID

from app.modules.clients.domain import Client, ClientNotFound, ClientRepository
from app.modules.instances.domain import (
    FINGERPRINT_MISMATCH,
    MANUAL_REASON,
    HeartbeatRepository,
    Instance,
    InstanceNotFound,
    InstanceRepository,
    InstanceRevoked,
    InstanceStatus,
    InstanceUnauthorized,
)
from app.shared.clock import Clock
from app.shared.sync_v1 import (
    HEARTBEAT_SECONDS,
    INGEST_SECONDS,
    MAX_BATCH_EVENTS,
    HeartbeatRequest,
    HeartbeatResponse,
    Notice,
    Policy,
)
from app.shared.tokens import INSTANCE_SECRET_PREFIX, generate_secret, hash_secret

PREVIOUS_SECRET_GRACE = timedelta(hours=24)

_WIRE_STATUS: dict[InstanceStatus, Literal["active", "suspended", "revoked"]] = {
    InstanceStatus.ACTIVE: "active",
    InstanceStatus.SUSPENDED: "suspended",
    InstanceStatus.REVOKED: "revoked",
}


def policy_for(status: InstanceStatus, client: Client | None = None) -> Policy:
    """Política vigente de una instancia: la general más la de su cliente."""
    return Policy(
        heartbeat_seconds=HEARTBEAT_SECONDS,
        ingest_seconds=INGEST_SECONDS,
        max_batch_events=MAX_BATCH_EVENTS,
        sync_enabled=status is InstanceStatus.ACTIVE,
        config_locked=client.config_locked if client else False,
        allow_local_cli=client.allow_local_cli if client else False,
        identity_mode=client.identity_mode.value if client else "pseudonym",
    )


class ListInstancesUseCase:
    def __init__(self, clients: ClientRepository, instances: InstanceRepository) -> None:
        self._clients = clients
        self._instances = instances

    async def execute(self, client_code: str) -> list[Instance]:
        client = await self._clients.get_by_code(client_code)
        if client is None:
            raise ClientNotFound(f"No existe el cliente {client_code}.")
        return await self._instances.list_by_client(client.id)


class AuthenticateInstanceUseCase:
    """Bearer -> instancia. Busca por SHA-256 y compara el hash en tiempo constante."""

    def __init__(self, instances: InstanceRepository, clock: Clock) -> None:
        self._instances = instances
        self._clock = clock

    async def execute(self, bearer: str) -> Instance:
        presented = hash_secret(bearer)
        instance = await self._instances.get_by_secret_hash(presented)
        if instance is None:
            raise InstanceUnauthorized("Secreto de instancia inválido.")
        if not self._matches(instance, presented):
            raise InstanceUnauthorized("Secreto de instancia inválido.")
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia fue revocada.")
        return instance

    def _matches(self, instance: Instance, presented: bytes) -> bool:
        if hmac.compare_digest(instance.secret_hash, presented):
            return True
        previous = instance.previous_secret_hash
        expires = instance.previous_secret_expires_at
        return (
            previous is not None
            and expires is not None
            and hmac.compare_digest(previous, presented)
            and self._clock() < expires
        )


class RecordHeartbeatUseCase:
    def __init__(
        self,
        instances: InstanceRepository,
        heartbeats: HeartbeatRepository,
        clock: Clock,
        clients: ClientRepository | None = None,
    ) -> None:
        self._instances = instances
        self._heartbeats = heartbeats
        self._clock = clock
        self._clients = clients

    async def execute(self, instance_id: UUID, payload: HeartbeatRequest) -> HeartbeatResponse:
        now = self._clock()
        instance = await self._instances.get_for_update(instance_id)
        if instance is None:
            raise InstanceUnauthorized("Secreto de instancia inválido.")
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia fue revocada.")

        status, reason = instance.status, instance.status_reason
        if status is InstanceStatus.ACTIVE and payload.fingerprint != instance.fingerprint:
            # Posible clon (R7): se suspende hasta que un administrador lo confirme.
            status, reason = InstanceStatus.SUSPENDED, FINGERPRINT_MISMATCH

        raw = payload.model_dump(mode="json")
        await self._instances.save(
            replace(
                instance,
                status=status,
                status_reason=reason,
                last_seen_at=now,
                last_heartbeat=raw,
                clock_skew_seconds=round((now - payload.sent_at).total_seconds()),
                version=payload.version or instance.version,
                commit=payload.commit or instance.commit,
                deployment_mode=payload.deployment_mode,
                updated_at=now,
            )
        )
        await self._heartbeats.add(instance.id, now, raw)

        notices: list[Notice] = []
        if status is InstanceStatus.SUSPENDED and reason == FINGERPRINT_MISMATCH:
            notices.append(
                Notice(
                    code="fingerprint_mismatch",
                    severity="critical",
                    message="La huella de la instancia cambió; un administrador debe confirmarla.",
                )
            )
        if status is InstanceStatus.ACTIVE and instance.rotation_requested_at is not None:
            notices.append(
                Notice(
                    code="rotate_credentials",
                    severity="info",
                    message="Cloud pidió renovar las credenciales de esta instalación.",
                )
            )
        client = await self._clients.get_by_id(instance.client_id) if self._clients else None
        return HeartbeatResponse(
            server_time=now,
            instance_status=_WIRE_STATUS[status],
            policy=policy_for(status, client),
            notices=notices,
        )


class RotateCredentialsUseCase:
    """Genera un secreto nuevo; el anterior sigue valiendo 24 h (§3.4)."""

    def __init__(self, instances: InstanceRepository, clock: Clock) -> None:
        self._instances = instances
        self._clock = clock

    async def execute(self, instance_id: UUID) -> str:
        now = self._clock()
        instance = await self._instances.get_for_update(instance_id)
        if instance is None:
            raise InstanceUnauthorized("Secreto de instancia inválido.")
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia fue revocada.")
        secret = generate_secret(INSTANCE_SECRET_PREFIX)
        await self._instances.save(
            replace(
                instance,
                secret_hash=hash_secret(secret),
                previous_secret_hash=instance.secret_hash,
                previous_secret_expires_at=now + PREVIOUS_SECRET_GRACE,
                rotation_requested_at=None,
                updated_at=now,
            )
        )
        return secret


class _ChangeStatusUseCase:
    def __init__(self, instances: InstanceRepository, clock: Clock) -> None:
        self._instances = instances
        self._clock = clock

    async def _load(self, instance_id: UUID) -> Instance:
        instance = await self._instances.get_for_update(instance_id)
        if instance is None:
            raise InstanceNotFound(f"No existe la instancia {instance_id}.")
        return instance


class SuspendInstanceUseCase(_ChangeStatusUseCase):
    async def execute(self, instance_id: UUID, reason: str = MANUAL_REASON) -> Instance:
        instance = await self._load(instance_id)
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia está revocada; no se puede suspender.")
        if instance.status is InstanceStatus.SUSPENDED:
            return instance  # idempotente
        updated = replace(
            instance,
            status=InstanceStatus.SUSPENDED,
            status_reason=reason,
            updated_at=self._clock(),
        )
        await self._instances.save(updated)
        return updated


class ActivateInstanceUseCase(_ChangeStatusUseCase):
    """Reactiva una instancia suspendida.

    Si estaba suspendida por `fingerprint_mismatch`, activar equivale a "es la misma máquina"
    (§3.2): se adopta la última huella informada, si no volvería a suspenderse en el
    siguiente heartbeat.
    """

    async def execute(self, instance_id: UUID) -> Instance:
        instance = await self._load(instance_id)
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia está revocada; la revocación es definitiva.")
        if instance.status is InstanceStatus.ACTIVE:
            return instance  # idempotente
        fingerprint = instance.fingerprint
        if instance.status_reason == FINGERPRINT_MISMATCH and instance.last_heartbeat:
            reported = instance.last_heartbeat.get("fingerprint")
            if isinstance(reported, str) and reported:
                fingerprint = reported
        updated = replace(
            instance,
            status=InstanceStatus.ACTIVE,
            status_reason=None,
            fingerprint=fingerprint,
            updated_at=self._clock(),
        )
        await self._instances.save(updated)
        return updated


class RevokeInstanceUseCase(_ChangeStatusUseCase):
    async def execute(self, instance_id: UUID) -> Instance:
        instance = await self._load(instance_id)
        if instance.status is InstanceStatus.REVOKED:
            return instance  # idempotente
        updated = replace(
            instance,
            status=InstanceStatus.REVOKED,
            status_reason=MANUAL_REASON,
            previous_secret_hash=None,
            previous_secret_expires_at=None,
            updated_at=self._clock(),
        )
        await self._instances.save(updated)
        return updated


class RequestRotationUseCase(_ChangeStatusUseCase):
    """Marca la instancia para que el próximo heartbeat le pida rotar su secreto."""

    async def execute(self, instance_id: UUID) -> Instance:
        instance = await self._load(instance_id)
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia está revocada; no hay secreto que rotar.")
        now = self._clock()
        updated = replace(instance, rotation_requested_at=now, updated_at=now)
        await self._instances.save(updated)
        return updated


class ConfirmFingerprintUseCase(_ChangeStatusUseCase):
    """Acepta la huella nueva ("es la misma máquina") y reactiva la instancia."""

    async def execute(self, instance_id: UUID) -> Instance:
        instance = await self._load(instance_id)
        if instance.status is InstanceStatus.REVOKED:
            raise InstanceRevoked("La instancia está revocada; la revocación es definitiva.")
        reported = (instance.last_heartbeat or {}).get("fingerprint")
        if not isinstance(reported, str) or not reported:
            raise InstanceNotFound("La instancia todavía no informó ninguna huella.")
        updated = replace(
            instance,
            status=InstanceStatus.ACTIVE,
            status_reason=None,
            fingerprint=reported,
            updated_at=self._clock(),
        )
        await self._instances.save(updated)
        return updated
