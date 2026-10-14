"""Vinculación, estados y backoff (§5.4, §5.6, §8.2)."""

from __future__ import annotations

import hashlib
import hmac
import random
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config import Settings
from app.infrastructure.database.base import Base
from app.modules.cloud_link.application.backoff import backoff_seconds
from app.modules.cloud_link.domain.entities import CloudNotice
from app.modules.cloud_link.domain.exceptions import (
    AlreadyLinkedError,
    CloudApiError,
    InsecureCloudUrlError,
)
from app.modules.cloud_link.domain.value_objects import HistoryMode, LinkStatus
from app.modules.cloud_link.infrastructure.composition import (
    CloudLinkServices,
    build_cloud_link_services,
)
from app.modules.cloud_link.infrastructure.persistence import CloudLinkModel
from app.modules.cloud_link.infrastructure.sync_lock import NoopSyncLock
from app.shared.exceptions.base import ValidationError

from .support import (
    CLOUD_URL,
    DB_A,
    NEW_SECRET,
    SECRET,
    T0,
    FakeClock,
    FakeCloudApi,
    add_conversation,
    add_message,
    http_error,
    net_error,
)

TOKEN = "svk_enr_" + "0" * 40


async def _link(services: CloudLinkServices, history: HistoryMode = HistoryMode.ALL) -> None:
    await services.link.execute(cloud_url=CLOUD_URL, token=TOKEN, history=history)


# ── backoff ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("failures", "base"),
    [(1, 30), (2, 60), (3, 120), (4, 240), (5, 480), (6, 960), (7, 1800), (12, 1800), (99, 1800)],
)
def test_backoff_is_exponential_capped_at_30_minutes_with_20_percent_jitter(
    failures: int, base: float
) -> None:
    rng = random.Random(1234)
    for _ in range(200):
        wait = backoff_seconds(failures, rng=rng)
        assert base * 0.8 <= wait <= base * 1.2


def test_backoff_jitter_actually_varies() -> None:
    rng = random.Random(7)
    assert len({round(backoff_seconds(3, rng=rng), 3) for _ in range(20)}) > 10


def test_retry_after_is_respected_over_the_exponential_schedule() -> None:
    assert backoff_seconds(1, retry_after_seconds=120) == 120
    assert backoff_seconds(9, retry_after_seconds=45) == 45
    # Un valor descabellado tiene techo.
    assert backoff_seconds(1, retry_after_seconds=10**9) == 3600


# ── vinculación ───────────────────────────────────────────────────────────


async def test_link_stores_the_instance_and_encrypts_the_secret(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi()
    services = make_services(api)

    state = await services.link.execute(cloud_url=CLOUD_URL + "/", token=f"  {TOKEN} ")

    assert state.status == LinkStatus.LINKED
    assert state.client_code == "FARMX" and state.client_name == "Farmacias X"
    assert state.secret == SECRET
    token, instance = api.enroll_calls[0]
    assert token == TOKEN
    assert instance["deployment_mode"] == "desktop"
    assert instance["agent_db_engine"] == "sqlite"
    assert instance["fingerprint"]
    # El secreto y la clave de seudónimos están cifrados en la tabla.
    async with sm() as session:
        row = (await session.execute(select(CloudLinkModel))).scalar_one()
    assert row.cloud_url == CLOUD_URL
    assert row.secret_encrypted and SECRET not in row.secret_encrypted
    assert row.pseudonym_key_encrypted and row.install_id is not None


async def test_linking_twice_is_a_validation_error(
    make_services: Callable[..., CloudLinkServices],
) -> None:
    services = make_services(FakeCloudApi())
    await _link(services)

    with pytest.raises(AlreadyLinkedError):
        await _link(services)
    assert issubclass(AlreadyLinkedError, ValidationError)  # 422


async def test_enroll_failure_is_recorded_without_leaving_a_half_link(
    make_services: Callable[..., CloudLinkServices],
) -> None:
    api = FakeCloudApi(enroll_error=http_error(404, "enrollment_token_invalid"))
    services = make_services(api)

    with pytest.raises(CloudApiError):
        await _link(services)

    state = await services.repository.get()
    assert state.status == LinkStatus.UNLINKED
    assert state.secret is None and state.instance_id is None
    assert state.last_error_code == "enrollment_token_invalid"


async def test_https_is_mandatory_outside_development(
    make_services: Callable[..., CloudLinkServices], make_settings: Callable[..., Settings]
) -> None:
    production = make_settings(
        app_env="production",
        agent_db_engine="postgresql",
        agent_db_host="localhost",
        agent_db_user="u",
        agent_db_password="p",
        agent_db_name="n",
        jwt_secret="j" * 48,
    )
    services = make_services(FakeCloudApi(), settings=production)

    with pytest.raises(InsecureCloudUrlError):
        await services.link.execute(cloud_url="http://cloud.example.test", token=TOKEN)


async def test_http_is_accepted_in_development(
    make_services: Callable[..., CloudLinkServices], make_settings: Callable[..., Settings]
) -> None:
    settings = make_settings(app_env="development")
    services = make_services(FakeCloudApi(), settings=settings)

    state = await services.link.execute(cloud_url="http://localhost:9000", token=TOKEN)

    assert state.cloud_url == "http://localhost:9000"


# ── estados ───────────────────────────────────────────────────────────────


async def test_revoked_response_deletes_the_local_secret_and_stops_everything(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    api.heartbeat_error = http_error(401, "instance_revoked")

    outcome = await services.heartbeat.execute()

    assert outcome.sent and not outcome.ok
    state = await services.repository.get()
    assert state.status == LinkStatus.REVOKED
    assert state.secret is None
    async with sm() as session:
        row = (await session.execute(select(CloudLinkModel))).scalar_one()
    assert row.secret_encrypted is None
    # Todo se detiene: ni heartbeat ni envío.
    api.heartbeat_error = None
    before = (len(api.heartbeats), len(api.ingests))
    assert not (await services.heartbeat.execute()).sent
    assert (await services.sync.execute()).skipped_reason == "not_syncing"
    assert (len(api.heartbeats), len(api.ingests)) == before


async def test_unauthorized_stops_syncing_but_the_heartbeat_can_recover(
    make_services: Callable[..., CloudLinkServices],
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    api.heartbeat_error = http_error(401, "instance_unauthorized")

    await services.heartbeat.execute()

    state = await services.repository.get()
    assert state.status == LinkStatus.UNAUTHORIZED
    assert state.last_error_code == "instance_unauthorized"
    assert (await services.sync.execute()).skipped_reason == "not_syncing"

    # Fue un fallo transitorio de Cloud: el heartbeat siguiente lo recupera.
    api.heartbeat_error = None
    await services.heartbeat.execute()
    assert (await services.repository.get()).status == LinkStatus.LINKED


async def test_suspended_keeps_the_heartbeat_but_stops_ingest_and_keeps_marks(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    conversation = await add_conversation(sm)
    await add_message(sm, conversation)
    await services.sync.execute()
    marks = {m.stream: m for m in await services.repository.list_watermarks()}
    ingests = len(api.ingests)

    api.instance_status = "suspended"
    await services.heartbeat.execute()
    assert (await services.repository.get()).status == LinkStatus.SUSPENDED
    await add_message(sm, conversation, created_at=T0 + timedelta(minutes=1))
    assert (await services.sync.execute()).skipped_reason == "not_syncing"

    assert len(api.ingests) == ingests
    assert {m.stream: m for m in await services.repository.list_watermarks()} == marks
    # El heartbeat sigue: así se entera de la reactivación.
    assert (await services.heartbeat.execute()).ok

    api.instance_status = "active"
    await services.heartbeat.execute()
    await services.sync.execute()
    assert len(api.unique_source_ids("turn/1")) == 2


async def test_15_minutes_without_heartbeat_goes_offline_and_recovers(
    make_services: Callable[..., CloudLinkServices], clock: FakeClock
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)

    api.heartbeat_error = net_error()
    clock.advance(minutes=14)
    await services.heartbeat.execute()
    assert (await services.repository.get()).status == LinkStatus.LINKED

    clock.advance(minutes=1)
    await services.heartbeat.execute()
    state = await services.repository.get()
    assert state.status == LinkStatus.OFFLINE
    assert state.consecutive_failures == 2
    # Offline todavía sincroniza: los eventos esperan en las tablas.
    assert state.status.syncs

    api.heartbeat_error = None
    await services.heartbeat.execute()
    state = await services.repository.get()
    assert state.status == LinkStatus.LINKED and state.consecutive_failures == 0


async def test_heartbeat_payload_follows_the_contract_and_carries_no_secrets(
    make_services: Callable[..., CloudLinkServices],
) -> None:
    from app.modules.cloud_link.infrastructure.contract_v1 import HeartbeatRequest

    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)
    await services.heartbeat.execute()

    payload = api.heartbeats[0]
    HeartbeatRequest.model_validate(payload)
    key = (await services.repository.get()).pseudonym_key
    text = str(payload)
    assert SECRET not in text and key.hex() not in text


async def test_policy_and_notices_from_the_heartbeat_are_stored(
    make_services: Callable[..., CloudLinkServices],
) -> None:
    from app.modules.cloud_link.domain.value_objects import SyncPolicy

    api = FakeCloudApi(
        policy=SyncPolicy(heartbeat_seconds=120, ingest_seconds=60, max_batch_events=200),
        notices=[CloudNotice("update_available", "info", "Hay una versión nueva.")],
    )
    services = make_services(api)
    await _link(services)
    await services.heartbeat.execute()

    state = await services.repository.get()
    assert state.effective_policy.max_batch_events == 200
    assert state.effective_policy.heartbeat_seconds == 120
    assert [n.code for n in state.notices] == ["update_available"]


# ── rotación ──────────────────────────────────────────────────────────────


async def test_rotation_notice_replaces_the_secret_before_anything_else(
    make_services: Callable[..., CloudLinkServices], clock: FakeClock
) -> None:
    api = FakeCloudApi(notices=[CloudNotice("rotate_credentials", "warning", "Rotá.")])
    services = make_services(api)
    await _link(services)
    clock.advance(hours=1)

    await services.heartbeat.execute()

    assert api.rotations == 1
    state = await services.repository.get()
    assert state.secret == NEW_SECRET
    assert state.secret_rotated_at == clock()


async def test_secret_is_rotated_automatically_every_90_days(
    make_services: Callable[..., CloudLinkServices], clock: FakeClock
) -> None:
    api = FakeCloudApi()
    services = make_services(api)
    await _link(services)

    clock.advance(days=89)
    await services.heartbeat.execute()
    assert api.rotations == 0

    clock.advance(days=1)
    await services.heartbeat.execute()
    assert api.rotations == 1


async def test_failed_rotation_keeps_the_current_secret(
    make_services: Callable[..., CloudLinkServices], clock: FakeClock
) -> None:
    api = FakeCloudApi(rotate_error=net_error())
    services = make_services(api)
    await _link(services)
    clock.advance(days=91)

    await services.heartbeat.execute()

    assert (await services.repository.get()).secret == SECRET


# ── seudónimo ─────────────────────────────────────────────────────────────


async def test_pseudonym_is_stable_distinct_between_databases_and_survives_unlinking(
    sm: async_sessionmaker[AsyncSession], make_services: Callable[..., CloudLinkServices]
) -> None:
    from app.modules.cloud_link.application.pseudonymizer import Pseudonymizer

    from .support import DB_B

    api = FakeCloudApi()
    services = make_services(api)
    # La clave existe ANTES de vincular.
    before_link = (await services.repository.get()).pseudonym_key
    assert len(before_link) == 32
    await _link(services)
    linked_key = (await services.repository.get()).pseudonym_key
    assert linked_key == before_link

    pseudonymizer = Pseudonymizer(linked_key)
    same = pseudonymizer.user_ref(DB_A, 7)
    assert same == pseudonymizer.user_ref(DB_A, 7)
    assert same != pseudonymizer.user_ref(DB_B, 7), "mismo idUsuario, otra base"
    assert same != pseudonymizer.user_ref(DB_A, 8)
    # Contra la fórmula del diseño.
    expected = hmac.new(linked_key, f"{DB_A}:7".encode(), hashlib.sha256).hexdigest()[:32]
    assert same == expected

    # Desvincular conserva la clave y el install_id; revincular da el mismo ref.
    install_id = (await services.repository.get()).install_id
    await services.unlink.execute()
    after_unlink = await services.repository.get()
    assert after_unlink.status == LinkStatus.UNLINKED
    assert after_unlink.secret is None and after_unlink.instance_id is None
    assert after_unlink.pseudonym_key == before_link
    assert after_unlink.install_id == install_id
    assert await services.repository.list_watermarks() == []

    await _link(services)
    relinked = await services.repository.get()
    assert Pseudonymizer(relinked.pseudonym_key).user_ref(DB_A, 7) == same
    assert relinked.install_id == install_id


async def test_two_installations_get_unrelated_pseudonym_keys(
    make_services: Callable[..., CloudLinkServices],
    make_settings: Callable[..., Settings],
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'otra.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        other_services = build_cloud_link_services(
            settings=make_settings(),
            sessionmaker=async_sessionmaker(bind=engine, expire_on_commit=False),
            cloud_api=FakeCloudApi(),
            sync_lock=NoopSyncLock(),
        )
        first = await make_services(FakeCloudApi()).repository.get()
        other = await other_services.repository.get()
        assert first.pseudonym_key != other.pseudonym_key
        assert first.install_id != other.install_id
    finally:
        await engine.dispose()
