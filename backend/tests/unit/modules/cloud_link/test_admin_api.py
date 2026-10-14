"""API de administración `/admin/cloud-link` (§6.1): permisos, estados,
errores de Cloud mapeados, ausencia de secretos y transparencia."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.main as main_module
from app.infrastructure.config import get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import get_current_user
from app.modules.cloud_link.infrastructure.composition import (
    CloudLinkServices,
    get_cloud_link_services,
)

from .support import (
    DB_A,
    NEW_SECRET,
    SECRET,
    T0,
    FakeClock,
    FakeCloudApi,
    add_conversation,
    add_free_query,
    add_message,
    add_session_token,
    http_error,
    net_error,
)

TOKEN = "svk_enr_" + "0" * 40
ROUTES: list[tuple[str, str]] = [
    ("GET", "/admin/cloud-link"),
    ("POST", "/admin/cloud-link"),
    ("DELETE", "/admin/cloud-link"),
    ("POST", "/admin/cloud-link/sync-now"),
    ("GET", "/admin/cloud-link/preview"),
]


def _user(*, admin: bool) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=1,
        login="ADMIN" if admin else "AGENTE",
        full_name="Nombre",
        is_admin=admin,
        is_active=True,
        erp_database_id=DB_A,
    )


@pytest.fixture
def api() -> FakeCloudApi:
    return FakeCloudApi()


@pytest.fixture
def services(
    make_services: Callable[..., CloudLinkServices], api: FakeCloudApi
) -> CloudLinkServices:
    return make_services(api)


@pytest.fixture
def make_client(
    services: CloudLinkServices, monkeypatch: pytest.MonkeyPatch
) -> Callable[[AuthenticatedUser], httpx.AsyncClient]:
    def build(user: AuthenticatedUser) -> httpx.AsyncClient:
        monkeypatch.setenv("SAVI_ADMIN_LOGINS", "")
        get_settings.cache_clear()
        app: FastAPI = main_module.create_app()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_cloud_link_services] = lambda: services
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://savi.test"
        )

    return build


@pytest_asyncio.fixture
async def admin(
    make_client: Callable[[AuthenticatedUser], httpx.AsyncClient],
) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(_user(admin=True)) as client:
        yield client
    get_settings.cache_clear()


def _assert_no_secrets(text: str, key: bytes) -> None:
    lowered = text.lower()
    assert "secret" not in lowered
    assert "pseudonym" not in lowered
    for leaked in (SECRET, NEW_SECRET, key.hex(), base64.b64encode(key).decode()):
        assert leaked not in text


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_every_route_is_403_without_admin(
    make_client: Callable[[AuthenticatedUser], httpx.AsyncClient], method: str, path: str
) -> None:
    async with make_client(_user(admin=False)) as client:
        response = await client.request(method, path, json={"token": TOKEN})

    assert response.status_code == 403


async def test_status_when_unlinked(admin: httpx.AsyncClient) -> None:
    response = await admin.get("/admin/cloud-link")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unlinked"
    assert body["cloud_configured"] is True
    assert body["instance_id"] is None and body["streams"] == []


async def test_link_returns_201_with_the_state_and_no_secrets(
    admin: httpx.AsyncClient, services: CloudLinkServices, api: FakeCloudApi
) -> None:
    response = await admin.post("/admin/cloud-link", json={"token": f" {TOKEN} "})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "linked"
    assert body["client_name"] == "Farmacias X" and body["client_code"] == "FARMX"
    assert {s["stream"] for s in body["streams"]} == {
        "turn",
        "conversation",
        "session",
        "free_query",
    }
    assert api.enroll_calls[0][0] == TOKEN
    key = (await services.repository.get()).pseudonym_key
    _assert_no_secrets(response.text, key)
    _assert_no_secrets((await admin.get("/admin/cloud-link")).text, key)


async def test_link_twice_is_422(admin: httpx.AsyncClient) -> None:
    await admin.post("/admin/cloud-link", json={"token": TOKEN})

    again = await admin.post("/admin/cloud-link", json={"token": TOKEN})

    assert again.status_code == 422
    assert "Desvinculá" in again.json()["detail"]


async def test_link_from_now_only_sends_what_comes_after(
    admin: httpx.AsyncClient,
    services: CloudLinkServices,
    sm: async_sessionmaker[AsyncSession],
    api: FakeCloudApi,
    clock: FakeClock,
) -> None:
    conversation = await add_conversation(sm, created_at=T0 - timedelta(days=3))
    await add_message(sm, conversation, created_at=T0 - timedelta(days=3))

    response = await admin.post("/admin/cloud-link", json={"token": TOKEN, "history": "from_now"})
    assert response.status_code == 201
    await services.sync.execute()
    assert api.events("turn/1") == []

    clock.advance(minutes=1)
    await add_message(sm, conversation, created_at=clock())
    await services.sync.execute()
    assert len(api.unique_source_ids("turn/1")) == 1


async def test_invalid_history_value_is_422(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/admin/cloud-link", json={"token": TOKEN, "history": "todo"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (http_error(404, "enrollment_token_invalid"), 404, "enrollment_token_invalid"),
        (http_error(403, "client_suspended"), 403, "client_suspended"),
        (net_error(), 502, "network_error"),
        (http_error(500, "cloud_unavailable"), 502, "cloud_unavailable"),
        (http_error(422, "validation_error"), 502, "contract_rejected"),
    ],
)
async def test_cloud_errors_are_mapped_for_the_administrator(
    admin: httpx.AsyncClient, api: FakeCloudApi, error: Any, status: int, code: str
) -> None:
    api.enroll_error = error

    response = await admin.post("/admin/cloud-link", json={"token": TOKEN})

    assert response.status_code == status
    assert response.json()["errorCode"] == code
    assert (await admin.get("/admin/cloud-link")).json()["status"] == "unlinked"


async def test_rate_limited_enrollment_forwards_retry_after(
    admin: httpx.AsyncClient, api: FakeCloudApi
) -> None:
    api.enroll_error = http_error(429, "too_many_requests", retry_after=120)

    response = await admin.post("/admin/cloud-link", json={"token": TOKEN})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "120"


async def test_unlink_returns_204_and_keeps_the_pseudonym_key(
    admin: httpx.AsyncClient, services: CloudLinkServices
) -> None:
    await admin.post("/admin/cloud-link", json={"token": TOKEN})
    key = (await services.repository.get()).pseudonym_key

    response = await admin.delete("/admin/cloud-link")

    assert response.status_code == 204
    assert (await admin.get("/admin/cloud-link")).json()["status"] == "unlinked"
    assert (await services.repository.get()).pseudonym_key == key


async def test_sync_now_is_202_and_runs_heartbeat_and_a_cycle(
    admin: httpx.AsyncClient,
    services: CloudLinkServices,
    api: FakeCloudApi,
    sm: async_sessionmaker[AsyncSession],
) -> None:
    await admin.post("/admin/cloud-link", json={"token": TOKEN})
    conversation = await add_conversation(sm)
    await add_message(sm, conversation)

    response = await admin.post("/admin/cloud-link/sync-now")
    await services.drain_background()

    assert response.status_code == 202
    assert len(api.heartbeats) == 1
    assert len(api.unique_source_ids("turn/1")) == 1


async def test_sync_now_when_unlinked_is_422(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/admin/cloud-link/sync-now")

    assert response.status_code == 422


async def test_preview_matches_what_the_cycle_sends_and_hides_secrets(
    admin: httpx.AsyncClient,
    services: CloudLinkServices,
    api: FakeCloudApi,
    sm: async_sessionmaker[AsyncSession],
) -> None:
    await admin.post("/admin/cloud-link", json={"token": TOKEN})
    conversation = await add_conversation(sm)
    await add_message(sm, conversation, role="user")
    await add_message(
        sm,
        conversation,
        created_at=T0 + timedelta(seconds=2),
        usage={"input_tokens": 11, "output_tokens": 3},
        cost="0.001",
        tools=[{"name": "consultar_datos", "status": "ok", "input": {"sql": "SELECT 1"}}],
    )
    await add_session_token(sm)
    await add_free_query(sm, conversation_id=conversation)

    response = await admin.get("/admin/cloud-link/preview")
    assert response.status_code == 200
    preview = response.json()

    await services.sync.execute()
    for stream, schema in (
        ("turn", "turn/1"),
        ("conversation", "conversation/1"),
        ("session", "session/1"),
        ("free_query", "free_query/1"),
        ("database", "database/1"),
    ):
        assert preview["events"][stream] == api.events(schema)[0], stream

    key = (await services.repository.get()).pseudonym_key
    _assert_no_secrets(response.text, key)
    text = json.dumps(preview, ensure_ascii=False)
    for content in ("Contenido que nunca debe viajar", "SELECT", "Juan Pérez", "USUARIO.REAL"):
        assert content not in text
    assert preview["heartbeat"]["sync"]["streams"].keys() >= {"turn"}
