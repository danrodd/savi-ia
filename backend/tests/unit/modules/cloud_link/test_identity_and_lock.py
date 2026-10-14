"""Política de Cloud sobre la instalación (M2): identidad de las personas y bloqueo.

Dos garantías opuestas que conviven:
- sin autorización de Cloud, el código de usuario **nunca** sale de esta base (RNF-04);
- con `config_locked`, la instalación queda solo con el chat aunque quien entre sea
  administrador.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.config import get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http import router as auth_router
from app.modules.auth.infrastructure.http.admin import (
    config_is_locked,
    require_platform_admin,
    require_unlocked_company_admin,
)
from app.modules.auth.infrastructure.http.dependencies import (
    get_current_user,
    get_reset_mfa_use_case,
)
from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.entities import EPOCH, Cursor
from app.modules.cloud_link.domain.entities.cloud_link_state import CloudLinkState
from app.modules.cloud_link.domain.value_objects import SyncPolicy
from app.modules.cloud_link.infrastructure.composition import (
    CloudLinkServices,
    init_cloud_link_services,
    reset_cloud_link_services,
)
from app.modules.cloud_link.infrastructure.contract_v1 import EVENT_MODELS
from app.modules.cloud_link.infrastructure.sources import SessionSource
from app.shared.exceptions import ConfigLockedError, register_exception_handlers
from app.shared.rate_limit import get_rate_limiter

from .contract_files import validate_document
from .support import FakeCloudApi, add_session_token

_START = Cursor(EPOCH, "")


@pytest.fixture
def services(make_services: Callable[..., CloudLinkServices]) -> CloudLinkServices:
    return make_services(FakeCloudApi())


async def _set_policy(services: CloudLinkServices, policy: SyncPolicy | None) -> None:
    def mutate(state: CloudLinkState) -> None:
        state.policy = policy

    await services.repository.update(mutate)


def _session_source(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> SessionSource:
    async def identity_mode() -> str:
        return (await services.repository.get()).effective_policy.identity_mode

    return SessionSource(sm, PseudonymizerProvider(services.repository), identity_mode)


# ── identidad ─────────────────────────────────────────────────────────────────────────────
async def test_without_authorization_the_login_never_leaves(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    await add_session_token(sm)
    source = _session_source(sm, services)

    [event] = await source.read_batch(_START, 10)

    assert "user_label" not in event.data
    assert "USUARIO.REAL" not in json.dumps(event.to_payload())


async def test_named_policy_adds_the_user_code_and_stays_within_the_contract(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    await add_session_token(sm)
    await _set_policy(services, SyncPolicy(identity_mode="named"))

    [event] = await _session_source(sm, services).read_batch(_START, 10)

    assert event.data["user_label"] == "USUARIO.REAL"
    payload = event.to_payload()
    EVENT_MODELS[payload["schema"]].model_validate(payload)
    validate_document("events/session", payload)
    # El código de usuario es lo único agregado: nada de nombre completo ni correo.
    assert set(event.data) == {"user_ref", "database_ref", "user_label"}


async def test_the_policy_is_read_on_every_batch(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    """Si Cloud revoca la autorización, el siguiente lote ya no lleva etiquetas."""
    await add_session_token(sm)
    source = _session_source(sm, services)

    await _set_policy(services, SyncPolicy(identity_mode="named"))
    assert "user_label" in (await source.read_batch(_START, 10))[0].data

    await _set_policy(services, SyncPolicy(identity_mode="pseudonym"))
    assert "user_label" not in (await source.read_batch(_START, 10))[0].data


async def test_source_without_a_provider_is_always_pseudonymous(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    await add_session_token(sm)
    await _set_policy(services, SyncPolicy(identity_mode="named"))
    source = SessionSource(sm, PseudonymizerProvider(services.repository))

    [event] = await source.read_batch(_START, 10)

    assert "user_label" not in event.data


# ── persistencia de la política ───────────────────────────────────────────────────────────
async def test_policy_survives_a_reload(services: CloudLinkServices) -> None:
    await _set_policy(services, SyncPolicy(config_locked=True, identity_mode="named"))

    policy = (await services.repository.get()).effective_policy

    assert policy.config_locked is True
    assert policy.identity_mode == "named"


async def test_a_policy_stored_before_this_change_defaults_to_open_and_pseudonymous(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    """Un `policy` guardado por una versión anterior no trae los campos nuevos."""
    # Se escribe el JSON tal cual lo dejaba la versión anterior.
    from sqlalchemy import update

    from app.modules.cloud_link.infrastructure.persistence.models import CloudLinkModel

    repo = services.repository
    await repo.get()  # crea la fila
    async with sm() as session:
        await session.execute(
            update(CloudLinkModel).values(
                policy={
                    "heartbeat_seconds": 300,
                    "ingest_seconds": 300,
                    "max_batch_events": 500,
                    "sync_enabled": True,
                }
            )
        )
        await session.commit()

    policy = (await repo.get()).effective_policy

    assert policy.config_locked is False
    assert policy.identity_mode == "pseudonym"


async def test_a_garbage_identity_mode_falls_back_to_pseudonym(
    sm: async_sessionmaker[AsyncSession], services: CloudLinkServices
) -> None:
    from sqlalchemy import update

    from app.modules.cloud_link.infrastructure.persistence.models import CloudLinkModel

    repo = services.repository
    await repo.get()
    async with sm() as session:
        await session.execute(
            update(CloudLinkModel).values(policy={"identity_mode": "todos", "config_locked": "si"})
        )
        await session.commit()

    policy = (await repo.get()).effective_policy

    # Ante la duda, lo más privado y lo más abierto para quien está bloqueado por error.
    assert policy.identity_mode == "pseudonym"
    assert policy.config_locked is False


# ── bloqueo ───────────────────────────────────────────────────────────────────────────────
ADMIN = AuthenticatedUser(
    id=1, erp_database_id=uuid4(), login="ADMIN", full_name="Admin", is_admin=True, is_active=True
)


@pytest.fixture
async def registered(services: CloudLinkServices) -> AsyncIterator[CloudLinkServices]:
    init_cloud_link_services(services)
    yield services
    reset_cloud_link_services()


async def test_not_locked_when_the_link_service_is_not_running() -> None:
    reset_cloud_link_services()
    assert await config_is_locked() is False


async def test_lock_follows_the_policy(registered: CloudLinkServices) -> None:
    assert await config_is_locked() is False

    await _set_policy(registered, SyncPolicy(config_locked=True))
    assert await config_is_locked() is True

    await _set_policy(registered, SyncPolicy(config_locked=False))
    assert await config_is_locked() is False


async def test_a_locked_installation_rejects_even_an_administrator(
    registered: CloudLinkServices,
) -> None:
    settings = get_settings()
    await _set_policy(registered, SyncPolicy(config_locked=True))

    with pytest.raises(ConfigLockedError):
        await require_platform_admin(ADMIN, settings)
    with pytest.raises(ConfigLockedError):
        await require_unlocked_company_admin(ADMIN, settings)


async def test_an_unlocked_installation_still_admits_the_administrator(
    registered: CloudLinkServices,
) -> None:
    settings = get_settings()

    assert await require_unlocked_company_admin(ADMIN, settings) is ADMIN


def _client(user: AuthenticatedUser) -> TestClient:
    from app.modules.auth.infrastructure.http.mfa_admin_routes import router as mfa_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(mfa_router)
    register_exception_handlers(app)
    app.dependency_overrides[get_current_user] = lambda: user
    # El caso de uso real necesita la base del agente; acá solo se prueba la compuerta, que
    # corta antes de usarlo.
    app.dependency_overrides[get_reset_mfa_use_case] = lambda: object()
    get_rate_limiter().reset()
    return TestClient(app)


async def test_policy_endpoint_tells_the_interface_whether_it_is_locked(
    registered: CloudLinkServices,
) -> None:
    client = _client(ADMIN)
    assert client.get("/auth/me/policy").json() == {"config_locked": False}

    await _set_policy(registered, SyncPolicy(config_locked=True))
    assert client.get("/auth/me/policy").json() == {"config_locked": True}


async def test_admin_api_answers_config_locked_with_its_own_error_code(
    registered: CloudLinkServices,
) -> None:
    await _set_policy(registered, SyncPolicy(config_locked=True))

    response = _client(ADMIN).post("/admin/mfa/reset", json={"login": "X"})

    assert response.status_code == 403
    assert response.json()["errorCode"] == "config_locked"
    assert "SEO Group" in response.json()["detail"]


# ── CLI de Claude local ───────────────────────────────────────────────────────────────────
async def _link(services: CloudLinkServices, policy: SyncPolicy) -> None:
    def mutate(state: CloudLinkState) -> None:
        state.instance_id = uuid4()
        state.secret = "svk_inst_secreto"
        state.policy = policy

    await services.repository.update(mutate)


async def test_local_cli_is_allowed_without_a_link(registered: CloudLinkServices) -> None:
    from app.modules.llm_providers.infrastructure.local_cli_policy import local_cli_allowed

    assert await local_cli_allowed(get_settings()) is True


async def test_local_cli_follows_the_cloud_policy_once_linked(
    registered: CloudLinkServices,
) -> None:
    from app.modules.llm_providers.infrastructure.local_cli_policy import local_cli_allowed

    settings = get_settings()
    await _link(registered, SyncPolicy(allow_local_cli=False))
    assert await local_cli_allowed(settings) is False

    await _link(registered, SyncPolicy(allow_local_cli=True))
    assert await local_cli_allowed(settings) is True


async def test_local_cli_is_off_in_a_deployment_that_disables_it(
    registered: CloudLinkServices,
) -> None:
    from app.modules.llm_providers.infrastructure.local_cli_policy import local_cli_allowed

    await _link(registered, SyncPolicy(allow_local_cli=True))
    settings = get_settings().model_copy(update={"local_cli_enabled": False})

    # El Master: manda el despliegue, aunque Cloud lo permita.
    assert await local_cli_allowed(settings) is False
