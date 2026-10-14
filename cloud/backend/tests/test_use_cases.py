"""Casos de uso con repositorios en memoria."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from uuid import uuid4

import pytest

from app.modules.clients.application import CreateClientUseCase, ListClientsUseCase
from app.modules.clients.domain import (
    Client,
    ClientCodeAlreadyExists,
    ClientNotFound,
    ClientStatus,
    ClientSuspended,
    InvalidClientCode,
    InvalidClientName,
)
from app.modules.enrollments.application import (
    CreateEnrollmentTokenUseCase,
    ListEnrollmentTokensUseCase,
    RedeemEnrollmentTokenUseCase,
    RevokeEnrollmentTokenUseCase,
)
from app.modules.enrollments.domain import (
    EnrollmentToken,
    EnrollmentTokenAlreadyUsed,
    EnrollmentTokenInvalid,
    EnrollmentTokenNotFound,
    InstanceInfo,
    InvalidExpiration,
    TokenState,
)
from app.modules.instances.application import ListInstancesUseCase
from app.shared.tokens import hash_secret
from tests.fakes import (
    FakeClientRepository,
    FakeClock,
    FakeEnrollmentTokenRepository,
    FakeInstanceRepository,
)

INFO = InstanceInfo(
    name="SRV-FARMX",
    deployment_mode="server",
    version="v1.2.0",
    commit="2ce0b85",
    os="Windows Server 2022",
    agent_db_engine="postgresql",
    fingerprint="fp-123",
)


class World:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.clients = FakeClientRepository()
        self.tokens = FakeEnrollmentTokenRepository()
        self.instances = FakeInstanceRepository()

    async def client(self, code: str = "FARMX") -> Client:
        return await CreateClientUseCase(self.clients, self.clock).execute(
            code=code, name="Farmacias X"
        )

    def create_token(self) -> CreateEnrollmentTokenUseCase:
        return CreateEnrollmentTokenUseCase(self.clients, self.tokens, self.clock)

    def redeem(self) -> RedeemEnrollmentTokenUseCase:
        return RedeemEnrollmentTokenUseCase(self.clients, self.tokens, self.instances, self.clock)


@pytest.fixture
def world() -> World:
    return World()


# --- clientes -------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["FARMX", "AB", "A_1", "X" * 32, "0123"])
async def test_valid_client_codes(world: World, code: str) -> None:
    client = await world.client(code)
    assert client.code == code
    assert client.status is ClientStatus.ACTIVE


@pytest.mark.parametrize("code", ["", "A", "farmx", "FARM X", "FARM-X", "X" * 33, "ÑANDU"])
async def test_invalid_client_codes(world: World, code: str) -> None:
    with pytest.raises(InvalidClientCode):
        await world.client(code)


async def test_client_code_must_be_unique(world: World) -> None:
    await world.client("FARMX")
    with pytest.raises(ClientCodeAlreadyExists):
        await world.client("FARMX")


async def test_client_name_is_required_and_trimmed(world: World) -> None:
    with pytest.raises(InvalidClientName):
        await CreateClientUseCase(world.clients, world.clock).execute(code="AB", name="   ")
    created = await CreateClientUseCase(world.clients, world.clock).execute(
        code="AB", name="  Acme  "
    )
    assert created.name == "Acme"


async def test_list_clients_sorted(world: World) -> None:
    await world.client("ZETA")
    await world.client("ALFA")
    codes = [c.code for c in await ListClientsUseCase(world.clients).execute()]
    assert codes == ["ALFA", "ZETA"]


# --- tokens ---------------------------------------------------------------------------


async def test_token_is_stored_only_as_hash(world: World) -> None:
    await world.client()
    created = await world.create_token().execute(client_code="FARMX")

    assert created.plaintext.startswith("svk_enr_")
    stored = world.tokens.items[created.token.id]
    assert stored.token_hash == hash_secret(created.plaintext)
    # El texto plano no aparece en ningún campo ni en la representación de la entidad.
    for f in fields(EnrollmentToken):
        assert created.plaintext not in str(getattr(stored, f.name))
    assert created.plaintext not in repr(stored)


async def test_default_expiration_is_72_hours_and_custom_is_honored(world: World) -> None:
    await world.client()
    default = await world.create_token().execute(client_code="FARMX")
    assert default.token.expires_at == world.clock.now + timedelta(hours=72)
    custom = await world.create_token().execute(client_code="FARMX", expires_hours=1)
    assert custom.token.expires_at == world.clock.now + timedelta(hours=1)


@pytest.mark.parametrize("hours", [0, -5, 24 * 365 + 1])
async def test_invalid_expiration(world: World, hours: int) -> None:
    await world.client()
    with pytest.raises(InvalidExpiration):
        await world.create_token().execute(client_code="FARMX", expires_hours=hours)


async def test_token_for_unknown_or_suspended_client(world: World) -> None:
    with pytest.raises(ClientNotFound):
        await world.create_token().execute(client_code="NOPE")
    client = await world.client()
    world.clients.items[client.id] = replace(client, status=ClientStatus.SUSPENDED)
    with pytest.raises(ClientSuspended):
        await world.create_token().execute(client_code="FARMX")


async def test_redeem_creates_instance_and_marks_token_used(world: World) -> None:
    client = await world.client()
    created = await world.create_token().execute(client_code="FARMX")

    result = await world.redeem().execute(token=created.plaintext, info=INFO)

    assert result.client.id == client.id
    assert result.instance_secret.startswith("svk_ins_")
    assert result.instance.secret_hash == hash_secret(result.instance_secret)
    assert result.instance_secret.encode() not in result.instance.secret_hash
    used = world.tokens.items[created.token.id]
    assert used.used_at == world.clock.now
    assert used.used_by_instance_id == result.instance.id
    assert used.state(world.clock.now) is TokenState.USED


async def test_token_is_single_use(world: World) -> None:
    await world.client()
    created = await world.create_token().execute(client_code="FARMX")
    await world.redeem().execute(token=created.plaintext, info=INFO)
    with pytest.raises(EnrollmentTokenInvalid):
        await world.redeem().execute(token=created.plaintext, info=INFO)
    assert len(world.instances.items) == 1


async def test_expired_token_is_rejected(world: World) -> None:
    await world.client()
    created = await world.create_token().execute(client_code="FARMX", expires_hours=1)
    world.clock.advance(hours=1)
    with pytest.raises(EnrollmentTokenInvalid):
        await world.redeem().execute(token=created.plaintext, info=INFO)
    assert world.instances.items == {}


async def test_unknown_expired_used_and_revoked_share_one_error(world: World) -> None:
    await world.client()
    messages: set[str] = set()
    codes: set[str] = set()

    async def attempt(token: str) -> None:
        try:
            await world.redeem().execute(token=token, info=INFO)
        except EnrollmentTokenInvalid as exc:
            messages.add(exc.message)
            codes.add(exc.code)

    await attempt("svk_enr_inexistente")
    expired = await world.create_token().execute(client_code="FARMX", expires_hours=1)
    revoked = await world.create_token().execute(client_code="FARMX")
    await RevokeEnrollmentTokenUseCase(world.tokens, world.clock).execute(revoked.token.id)
    await attempt(revoked.plaintext)
    world.clock.advance(hours=2)
    await attempt(expired.plaintext)
    assert codes == {"enrollment_token_invalid"}
    assert len(messages) == 1


async def test_revoke_blocks_redeem_and_is_idempotent(world: World) -> None:
    await world.client()
    created = await world.create_token().execute(client_code="FARMX")
    revoke = RevokeEnrollmentTokenUseCase(world.tokens, world.clock)
    first = await revoke.execute(created.token.id)
    world.clock.advance(minutes=5)
    second = await revoke.execute(created.token.id)
    assert first.revoked_at == second.revoked_at
    with pytest.raises(EnrollmentTokenInvalid):
        await world.redeem().execute(token=created.plaintext, info=INFO)


async def test_cannot_revoke_used_or_unknown_token(world: World) -> None:
    await world.client()
    created = await world.create_token().execute(client_code="FARMX")
    await world.redeem().execute(token=created.plaintext, info=INFO)
    revoke = RevokeEnrollmentTokenUseCase(world.tokens, world.clock)
    with pytest.raises(EnrollmentTokenAlreadyUsed):
        await revoke.execute(created.token.id)
    with pytest.raises(EnrollmentTokenNotFound):
        await revoke.execute(uuid4())


async def test_suspended_client_cannot_redeem_and_token_is_kept(world: World) -> None:
    client = await world.client()
    created = await world.create_token().execute(client_code="FARMX")
    world.clients.items[client.id] = replace(client, status=ClientStatus.SUSPENDED)
    with pytest.raises(ClientSuspended):
        await world.redeem().execute(token=created.plaintext, info=INFO)
    assert world.tokens.items[created.token.id].used_at is None


async def test_list_tokens_and_instances(world: World) -> None:
    await world.client()
    await world.client("OTRO")
    a = await world.create_token().execute(client_code="FARMX")
    await world.create_token().execute(client_code="OTRO")
    await world.redeem().execute(token=a.plaintext, info=INFO)

    tokens = await ListEnrollmentTokensUseCase(world.clients, world.tokens).execute("FARMX")
    assert [t.id for t in tokens] == [a.token.id]
    instances = await ListInstancesUseCase(world.clients, world.instances).execute("FARMX")
    assert [i.name for i in instances] == ["SRV-FARMX"]
    assert await ListInstancesUseCase(world.clients, world.instances).execute("OTRO") == []
    with pytest.raises(ClientNotFound):
        await ListInstancesUseCase(world.clients, world.instances).execute("NOPE")
