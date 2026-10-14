"""Cliente `httpx` de SAVI Cloud: cabeceras, gzip, timeouts, TLS y errores."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.modules.cloud_link.domain.exceptions import CloudApiError, InsecureCloudUrlError
from app.modules.cloud_link.infrastructure import http_cloud_api as module
from app.modules.cloud_link.infrastructure.http_cloud_api import HttpxCloudApi

from .support import SECRET

URL = "https://cloud.example.test"
INSTANCE_ID = "8f0c2d4e-1a2b-4c3d-8e4f-5a6b7c8d9e0f"
POLICY = {
    "heartbeat_seconds": 300,
    "ingest_seconds": 300,
    "max_batch_events": 500,
    "sync_enabled": True,
}


def _api(
    handler: Callable[[httpx.Request], httpx.Response], *, allow_insecure_http: bool = False
) -> tuple[HttpxCloudApi, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    api = HttpxCloudApi(
        allow_insecure_http=allow_insecure_http, transport=httpx.MockTransport(wrapped)
    )
    return api, seen


async def test_enroll_posts_the_token_and_parses_the_response() -> None:
    api, seen = _api(
        lambda r: httpx.Response(
            201,
            json={
                "instance_id": INSTANCE_ID,
                "instance_secret": SECRET,
                "client": {"id": INSTANCE_ID, "code": "FARMX", "name": "Farmacias X"},
                "policy": POLICY,
            },
        )
    )

    result = await api.enroll(
        cloud_url=URL + "/", token="svk_enr_x", instance={"name": "SRV", "fingerprint": "f"}
    )

    request = seen[0]
    assert str(request.url) == f"{URL}/api/v1/enrollments/redeem"
    assert "authorization" not in request.headers
    assert json.loads(request.content) == {
        "token": "svk_enr_x",
        "instance": {"name": "SRV", "fingerprint": "f"},
    }
    assert str(result.instance_id) == INSTANCE_ID
    assert result.instance_secret == SECRET and result.client_code == "FARMX"
    assert result.policy.max_batch_events == 500


async def test_heartbeat_sends_the_bearer_and_parses_status_policy_and_notices() -> None:
    api, seen = _api(
        lambda r: httpx.Response(
            200,
            json={
                "server_time": "2026-10-14T12:00:01Z",
                "instance_status": "suspended",
                "policy": POLICY,
                "notices": [{"code": "update_available", "severity": "info", "message": "Hay."}],
                "ai": None,
                "campo_nuevo_de_cloud": 1,
            },
        )
    )

    result = await api.heartbeat(cloud_url=URL, secret=SECRET, payload={"sent_at": "x"})

    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"
    assert result.instance_status == "suspended"
    assert [n.code for n in result.notices] == ["update_available"]


async def test_ingest_is_gzipped_json_with_the_batch_id() -> None:
    api, seen = _api(
        lambda r: httpx.Response(
            200,
            json={
                "accepted": 1,
                "duplicates": 1,
                "rejected": [{"source_id": "e", "reason": "invalid_event"}],
            },
        )
    )
    batch_id = "0b8e6d0a-1d49-4ab0-9c9f-0c2e57b5a111"

    result = await api.ingest(
        cloud_url=URL,
        secret=SECRET,
        batch_id=batch_id,
        sent_at=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        events=[{"schema": "turn/1", "source_id": "a", "occurred_at": "x", "data": {}}],
    )

    request = seen[0]
    assert request.headers["content-encoding"] == "gzip"
    assert request.headers["content-type"] == "application/json"
    body = json.loads(gzip.decompress(request.content))
    assert body["batch_id"] == batch_id
    assert body["sent_at"] == "2026-10-14T12:00:00Z"
    assert body["events"][0]["source_id"] == "a"
    assert (result.accepted, result.duplicates) == (1, 1)
    assert [(r.source_id, r.reason) for r in result.rejected] == [("e", "invalid_event")]


async def test_an_oversized_payload_is_a_413_before_leaving_the_machine() -> None:
    api, seen = _api(lambda r: httpx.Response(200, json={}))
    big = {"schema": "turn/1", "source_id": "a", "occurred_at": "x", "data": {"x": "y" * 6_000_000}}

    with pytest.raises(CloudApiError) as raised:
        await api.ingest(
            cloud_url=URL, secret=SECRET, batch_id="b", sent_at=datetime.now(UTC), events=[big]
        )

    assert raised.value.status_code == 413
    assert seen == []


async def test_rotate_returns_the_new_secret() -> None:
    api, seen = _api(lambda r: httpx.Response(200, json={"instance_secret": "nuevo"}))

    assert await api.rotate(cloud_url=URL, secret=SECRET) == "nuevo"
    assert str(seen[0].url) == f"{URL}/api/v1/instances/credentials/rotate"


@pytest.mark.parametrize(
    ("response", "status", "code", "transient"),
    [
        (
            httpx.Response(401, json={"errorCode": "instance_revoked", "message": "x"}),
            401,
            "instance_revoked",
            False,
        ),
        (
            httpx.Response(401, json={"errorCode": "instance_unauthorized"}),
            401,
            "instance_unauthorized",
            False,
        ),
        (httpx.Response(401, text="no es json"), 401, "instance_unauthorized", False),
        (httpx.Response(413, json={"errorCode": "batch_too_large"}), 413, "batch_too_large", False),
        (
            httpx.Response(422, json={"errorCode": "invalid_envelope"}),
            422,
            "invalid_envelope",
            False,
        ),
        (httpx.Response(503, text="<html>"), 503, "cloud_unavailable", True),
        # Un `errorCode` con texto libre no se guarda tal cual.
        (
            httpx.Response(500, json={"errorCode": "Falló: datos del cliente X"}),
            500,
            "cloud_unavailable",
            True,
        ),
    ],
)
async def test_error_responses_become_short_codes(
    response: httpx.Response, status: int, code: str, transient: bool
) -> None:
    api, _ = _api(lambda r: response)

    with pytest.raises(CloudApiError) as raised:
        await api.heartbeat(cloud_url=URL, secret=SECRET, payload={})

    error = raised.value
    assert (error.status_code, error.error_code, error.is_transient) == (status, code, transient)


async def test_retry_after_header_is_read_as_seconds() -> None:
    api, _ = _api(
        lambda r: httpx.Response(
            429, json={"errorCode": "too_many_requests"}, headers={"Retry-After": "45"}
        )
    )

    with pytest.raises(CloudApiError) as raised:
        await api.heartbeat(cloud_url=URL, secret=SECRET, payload={})

    assert raised.value.retry_after_seconds == 45.0
    assert raised.value.is_transient


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ConnectError("sin red"), "network_error"),
        (httpx.ConnectTimeout("lento"), "timeout"),
        (httpx.ReadTimeout("lento"), "timeout"),
        (httpx.ProxyError("proxy"), "network_error"),
    ],
)
async def test_transport_failures_are_transient_codes(exception: Exception, code: str) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise exception

    api, _ = _api(boom)

    with pytest.raises(CloudApiError) as raised:
        await api.heartbeat(cloud_url=URL, secret=SECRET, payload={})

    assert raised.value.error_code == code
    assert raised.value.status_code is None and raised.value.is_transient


async def test_a_200_outside_the_contract_is_a_transient_error() -> None:
    api, _ = _api(lambda r: httpx.Response(200, json={"hola": "mundo"}))

    with pytest.raises(CloudApiError) as raised:
        await api.heartbeat(cloud_url=URL, secret=SECRET, payload={})

    assert raised.value.error_code == "invalid_response" and raised.value.is_transient


async def test_plain_http_is_rejected_unless_development() -> None:
    api, seen = _api(lambda r: httpx.Response(200, json={"instance_secret": "x"}))

    with pytest.raises(InsecureCloudUrlError):
        await api.rotate(cloud_url="http://cloud.example.test", secret=SECRET)
    assert seen == []

    dev, _ = _api(
        lambda r: httpx.Response(200, json={"instance_secret": "x"}), allow_insecure_http=True
    )
    assert await dev.rotate(cloud_url="http://localhost:9000", secret=SECRET) == "x"


async def test_client_uses_the_documented_timeouts_proxy_env_and_verifies_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    real = httpx.AsyncClient

    class Spy(real):  # type: ignore[valid-type, misc]
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", Spy)
    api, _ = _api(lambda r: httpx.Response(200, json={"instance_secret": "x"}))

    await api.rotate(cloud_url=URL, secret=SECRET)

    timeout: httpx.Timeout = captured["timeout"]
    assert timeout.connect == 10.0 and timeout.read == 30.0
    assert captured["trust_env"] is True
    # La verificación TLS nunca se desactiva.
    assert captured.get("verify", True) is True
