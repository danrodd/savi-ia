"""Acciones de la consola. Cada escritura se audita en la **misma** transacción.

No abren transacciones: lo hace la ruta HTTP. Si la auditoría falla, falla la acción.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.modules.audit.application import AuditRecorder
from app.modules.audit.domain import RequestContext
from app.modules.clients.application import CreateClientUseCase
from app.modules.clients.domain import (
    Client,
    ClientNotFound,
    ClientRepository,
    ClientStatus,
    IdentityMode,
    InvalidClientName,
)
from app.modules.clients.policies import AccessPolicy, AiPolicy, ensure_caps_fit
from app.modules.enrollments.application import (
    CreatedEnrollmentToken,
    CreateEnrollmentTokenUseCase,
    RevokeEnrollmentTokenUseCase,
)
from app.modules.enrollments.domain import EnrollmentToken, EnrollmentTokenRepository
from app.modules.instances.application import (
    ActivateInstanceUseCase,
    ConfirmFingerprintUseCase,
    RequestRotationUseCase,
    RevokeInstanceUseCase,
    SuspendInstanceUseCase,
)
from app.modules.instances.domain import (
    CLIENT_SUSPENDED_REASON,
    Instance,
    InstanceRepository,
    InstanceStatus,
)
from app.modules.staff.application import AuthDeps, CreatedStaff, CreateStaffUseCase
from app.modules.staff.domain import (
    InvalidStaffData,
    LastAdminProtected,
    Role,
    StaffNotFound,
    StaffUser,
)
from app.shared.clock import Clock


def _client_state(client: Client) -> dict[str, Any]:
    return {
        "code": client.code,
        "name": client.name,
        "nit": client.nit,
        "status": client.status.value,
    }


def _instance_state(instance: Instance) -> dict[str, Any]:
    return {"status": instance.status.value, "status_reason": instance.status_reason}


@dataclass(frozen=True)
class ClientActions:
    clients: ClientRepository
    instances: InstanceRepository
    audit: AuditRecorder
    clock: Clock

    async def create(self, *, code: str, name: str, nit: str | None, ctx: RequestContext) -> Client:
        client = await CreateClientUseCase(self.clients, self.clock).execute(
            code=code, name=name, nit=nit
        )
        await self.audit.record(
            ctx,
            "client.create",
            target_type="client",
            target_id=str(client.id),
            after=_client_state(client),
        )
        return client

    async def _get(self, client_id: UUID) -> Client:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            raise ClientNotFound("No existe el cliente.")
        return client

    async def update(
        self,
        client_id: UUID,
        *,
        name: str | None,
        nit: str | None,
        nit_given: bool,
        ctx: RequestContext,
    ) -> Client:
        client = await self._get(client_id)
        new_name = client.name
        if name is not None:
            new_name = name.strip()
            if not new_name or len(new_name) > 200:
                raise InvalidClientName("El nombre es obligatorio y admite hasta 200 caracteres.")
        new_nit = client.nit
        if nit_given:
            new_nit = nit.strip() if nit and nit.strip() else None
        updated = replace(client, name=new_name, nit=new_nit, updated_at=self.clock())
        await self.clients.save(updated)
        await self.audit.record(
            ctx,
            "client.update",
            target_type="client",
            target_id=str(client_id),
            before=_client_state(client),
            after=_client_state(updated),
        )
        return updated

    async def set_policy(
        self,
        client_id: UUID,
        *,
        identity_mode: IdentityMode | None,
        config_locked: bool | None,
        allow_local_cli: bool | None = None,
        ctx: RequestContext,
    ) -> Client:
        """Cambia la política que baja a las instalaciones del cliente (heartbeat).

        `named` guarda el código de usuario de cada persona: solo corresponde a la organización
        interna. Por eso es una acción propia, de administrador y auditada.
        """
        client = await self._get(client_id)
        updated = replace(
            client,
            identity_mode=identity_mode or client.identity_mode,
            config_locked=client.config_locked if config_locked is None else config_locked,
            allow_local_cli=(
                client.allow_local_cli if allow_local_cli is None else allow_local_cli
            ),
            updated_at=self.clock(),
        )
        await self.clients.save(updated)
        await self.audit.record(
            ctx,
            "client.policy",
            target_type="client",
            target_id=str(client_id),
            before={
                "identity_mode": client.identity_mode.value,
                "config_locked": client.config_locked,
                "allow_local_cli": client.allow_local_cli,
            },
            after={
                "identity_mode": updated.identity_mode.value,
                "config_locked": updated.config_locked,
                "allow_local_cli": updated.allow_local_cli,
            },
        )
        return updated

    async def set_ai_policy(
        self, client_id: UUID, policy: AiPolicy, *, ctx: RequestContext
    ) -> Client:
        """Reemplaza los proveedores permitidos y los topes de IA del cliente.

        Cloud decide; la instancia mide y bloquea antes de abrir el chat. Es una decisión de
        dinero y de acceso: de administrador y auditada con el antes y el después.
        """
        client = await self._get(client_id)
        ensure_caps_fit(policy, client.access_policy)
        updated = replace(client, ai_policy=policy, updated_at=self.clock())
        await self.clients.save(updated)
        await self.audit.record(
            ctx,
            "client.ai_policy",
            target_type="client",
            target_id=str(client_id),
            before=client.ai_policy.to_json(),
            after=updated.ai_policy.to_json(),
        )
        return updated

    async def set_access_policy(
        self, client_id: UUID, policy: AccessPolicy, *, ctx: RequestContext
    ) -> Client:
        """Reemplaza qué bases puede consultar cada persona (solo restringe lo que da el ERP)."""
        client = await self._get(client_id)
        ensure_caps_fit(client.ai_policy, policy)
        updated = replace(client, access_policy=policy, updated_at=self.clock())
        await self.clients.save(updated)
        await self.audit.record(
            ctx,
            "client.access_policy",
            target_type="client",
            target_id=str(client_id),
            before=client.access_policy.to_json(),
            after=updated.access_policy.to_json(),
        )
        return updated

    async def suspend(self, client_id: UUID, ctx: RequestContext) -> Client:
        """Suspende al cliente y a **todas** sus instancias (motivo `client_suspended`)."""
        client = await self._get(client_id)
        if client.status is ClientStatus.SUSPENDED:
            return client
        updated = replace(client, status=ClientStatus.SUSPENDED, updated_at=self.clock())
        await self.clients.save(updated)
        suspend = SuspendInstanceUseCase(self.instances, self.clock)
        affected = 0
        for instance in await self.instances.list_by_client(client_id):
            if instance.status is InstanceStatus.ACTIVE:
                await suspend.execute(instance.id, reason=CLIENT_SUSPENDED_REASON)
                affected += 1
        await self.audit.record(
            ctx,
            "client.suspend",
            target_type="client",
            target_id=str(client_id),
            before=_client_state(client),
            after={**_client_state(updated), "instances_suspended": affected},
        )
        return updated

    async def activate(self, client_id: UUID, ctx: RequestContext) -> Client:
        """Reactiva al cliente y solo las instancias que **él** suspendió."""
        client = await self._get(client_id)
        if client.status is ClientStatus.ACTIVE:
            return client
        updated = replace(client, status=ClientStatus.ACTIVE, updated_at=self.clock())
        await self.clients.save(updated)
        activate = ActivateInstanceUseCase(self.instances, self.clock)
        affected = 0
        for instance in await self.instances.list_by_client(client_id):
            if (
                instance.status is InstanceStatus.SUSPENDED
                and instance.status_reason == CLIENT_SUSPENDED_REASON
            ):
                await activate.execute(instance.id)
                affected += 1
        await self.audit.record(
            ctx,
            "client.activate",
            target_type="client",
            target_id=str(client_id),
            before=_client_state(client),
            after={**_client_state(updated), "instances_activated": affected},
        )
        return updated


@dataclass(frozen=True)
class InstanceActions:
    instances: InstanceRepository
    audit: AuditRecorder
    clock: Clock

    async def suspend(self, instance_id: UUID, ctx: RequestContext) -> Instance:
        before = await self.instances.get_by_id(instance_id)
        updated = await SuspendInstanceUseCase(self.instances, self.clock).execute(instance_id)
        await self._audit(ctx, "instance.suspend", before, updated)
        return updated

    async def activate(self, instance_id: UUID, ctx: RequestContext) -> Instance:
        before = await self.instances.get_by_id(instance_id)
        updated = await ActivateInstanceUseCase(self.instances, self.clock).execute(instance_id)
        await self._audit(ctx, "instance.activate", before, updated)
        return updated

    async def revoke(self, instance_id: UUID, ctx: RequestContext) -> Instance:
        before = await self.instances.get_by_id(instance_id)
        updated = await RevokeInstanceUseCase(self.instances, self.clock).execute(instance_id)
        await self._audit(ctx, "instance.revoke", before, updated)
        return updated

    async def confirm_fingerprint(self, instance_id: UUID, ctx: RequestContext) -> Instance:
        before = await self.instances.get_by_id(instance_id)
        updated = await ConfirmFingerprintUseCase(self.instances, self.clock).execute(instance_id)
        await self._audit(ctx, "instance.confirm_fingerprint", before, updated)
        return updated

    async def request_rotation(self, instance_id: UUID, ctx: RequestContext) -> Instance:
        before = await self.instances.get_by_id(instance_id)
        updated = await RequestRotationUseCase(self.instances, self.clock).execute(instance_id)
        await self._audit(ctx, "instance.request_rotation", before, updated)
        return updated

    async def _audit(
        self, ctx: RequestContext, action: str, before: Instance | None, after: Instance
    ) -> None:
        await self.audit.record(
            ctx,
            action,
            target_type="instance",
            target_id=str(after.id),
            before=_instance_state(before) if before else None,
            after=_instance_state(after),
        )


@dataclass(frozen=True)
class TokenActions:
    clients: ClientRepository
    tokens: EnrollmentTokenRepository
    audit: AuditRecorder
    clock: Clock
    default_expires_hours: int

    async def create(
        self, client_id: UUID, *, expires_hours: int, created_by: str, ctx: RequestContext
    ) -> CreatedEnrollmentToken:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            raise ClientNotFound("No existe el cliente.")
        created = await CreateEnrollmentTokenUseCase(
            self.clients,
            self.tokens,
            self.clock,
            default_expires_hours=self.default_expires_hours,
        ).execute(client_code=client.code, expires_hours=expires_hours, created_by=created_by)
        await self.audit.record(
            ctx,
            "token.create",
            target_type="enrollment_token",
            target_id=str(created.token.id),
            after={"client": client.code, "expires_at": created.token.expires_at.isoformat()},
        )
        return created

    async def list(self, client_id: UUID) -> list[EnrollmentToken]:
        if await self.clients.get_by_id(client_id) is None:
            raise ClientNotFound("No existe el cliente.")
        return await self.tokens.list_by_client(client_id)

    async def revoke(self, token_id: UUID, ctx: RequestContext) -> EnrollmentToken:
        revoked = await RevokeEnrollmentTokenUseCase(self.tokens, self.clock).execute(token_id)
        await self.audit.record(
            ctx, "token.revoke", target_type="enrollment_token", target_id=str(token_id)
        )
        return revoked


@dataclass(frozen=True)
class StaffActions:
    deps: AuthDeps

    async def create(
        self, *, email: str, full_name: str, role: Role, ctx: RequestContext
    ) -> CreatedStaff:
        return await CreateStaffUseCase(self.deps).execute(
            email=email, full_name=full_name, role=role, ctx=ctx
        )

    async def _get(self, staff_id: UUID) -> StaffUser:
        user = await self.deps.users.get_by_id(staff_id)
        if user is None:
            raise StaffNotFound("No existe el usuario.")
        return user

    async def _ensure_another_admin(self, user: StaffUser) -> None:
        """No se puede dejar el sistema sin administradores activos."""
        if (
            user.role is Role.ADMIN
            and user.is_active
            and await self.deps.users.count_active_admins() <= 1
        ):
            raise LastAdminProtected("Tiene que quedar al menos un administrador activo.")

    async def update(
        self,
        staff_id: UUID,
        *,
        full_name: str | None,
        role: Role | None,
        ctx: RequestContext,
    ) -> StaffUser:
        user = await self._get(staff_id)
        new_name = user.full_name
        if full_name is not None:
            new_name = full_name.strip()
            if not new_name or len(new_name) > 200:
                raise InvalidStaffData("El nombre es obligatorio y admite hasta 200 caracteres.")
        new_role = user.role
        if role is not None and role is not user.role:
            if staff_id == ctx.actor_staff_id:
                raise InvalidStaffData("No podés cambiar tu propio rol.")
            await self._ensure_another_admin(user)
            new_role = role  # los permisos se leen de la BD en cada request
        updated = replace(user, full_name=new_name, role=new_role, updated_at=self.deps.clock())
        await self.deps.users.save(updated)
        await self.deps.audit.record(
            ctx,
            "staff.update",
            target_type="staff",
            target_id=str(staff_id),
            before={"full_name": user.full_name, "role": user.role.value},
            after={"full_name": updated.full_name, "role": updated.role.value},
        )
        return updated

    async def deactivate(self, staff_id: UUID, ctx: RequestContext) -> StaffUser:
        user = await self._get(staff_id)
        if staff_id == ctx.actor_staff_id:
            raise InvalidStaffData("No podés desactivar tu propia cuenta.")
        if not user.is_active:
            return user
        await self._ensure_another_admin(user)
        now = self.deps.clock()
        updated = replace(user, is_active=False, updated_at=now)
        await self.deps.users.save(updated)
        await self.deps.sessions.revoke_all_of_user(staff_id, now)
        await self.deps.audit.record(
            ctx,
            "staff.deactivate",
            target_type="staff",
            target_id=str(staff_id),
            before={"is_active": True},
            after={"is_active": False},
        )
        return updated

    async def activate(self, staff_id: UUID, ctx: RequestContext) -> StaffUser:
        user = await self._get(staff_id)
        if user.is_active:
            return user
        updated = replace(
            user, is_active=True, failed_attempts=0, locked_until=None, updated_at=self.deps.clock()
        )
        await self.deps.users.save(updated)
        await self.deps.audit.record(
            ctx,
            "staff.activate",
            target_type="staff",
            target_id=str(staff_id),
            before={"is_active": False},
            after={"is_active": True},
        )
        return updated

    async def reset_mfa(self, staff_id: UUID, ctx: RequestContext) -> StaffUser:
        """Borra el TOTP: en el próximo ingreso tendrá que configurarlo de nuevo."""
        user = await self._get(staff_id)
        now = self.deps.clock()
        updated = replace(
            user,
            totp_secret_encrypted=None,
            totp_enabled_at=None,
            totp_last_step=0,
            updated_at=now,
        )
        await self.deps.users.save(updated)
        await self.deps.sessions.revoke_all_of_user(staff_id, now)
        await self.deps.audit.record(
            ctx, "staff.reset_mfa", target_type="staff", target_id=str(staff_id)
        )
        return updated
