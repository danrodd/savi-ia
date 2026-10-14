"""Vinculación automática al arrancar con el token del `.env` (§6.2, §8.2
"Instalador") y limpieza segura de la variable."""

from __future__ import annotations

import asyncio
import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from app.infrastructure.config import Settings
from app.modules.cloud_link.domain.value_objects import LinkStatus
from app.modules.cloud_link.infrastructure import scheduler as scheduler_module
from app.modules.cloud_link.infrastructure.composition import CloudLinkServices
from app.modules.cloud_link.infrastructure.env_file import clear_env_variable
from app.modules.cloud_link.infrastructure.scheduler import CloudLinkScheduler
from app.modules.cloud_link.infrastructure.startup import TOKEN_ENV_KEY, link_from_settings

from .support import CLOUD_URL, FakeCloudApi, http_error, net_error

TOKEN = "svk_enr_" + "0" * 40
ENV_LINES = [
    "APP_ENV=development\r\n",
    "ERP_DB_PASSWORD='con espacios y # numeral'\r\n",
    f"{TOKEN_ENV_KEY}='{TOKEN}'\r\n",
    "SAVI_CLOUD_URL=https://cloud.example.test\r\n",
]


def _env_file(tmp_path: Path, lines: list[str] = ENV_LINES) -> Path:
    path = tmp_path / ".env"
    path.write_bytes("".join(lines).encode("utf-8"))
    return path


@pytest.fixture
def with_token(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(savi_cloud_enrollment_token=TOKEN)


# ── limpieza del .env ─────────────────────────────────────────────────────


def test_clear_rewrites_only_that_line_and_keeps_the_rest_byte_for_byte(tmp_path: Path) -> None:
    path = _env_file(tmp_path)

    assert clear_env_variable(path, TOKEN_ENV_KEY) is True

    after = path.read_bytes().decode("utf-8")
    assert after == "".join(
        [
            ENV_LINES[0],
            ENV_LINES[1],
            f"{TOKEN_ENV_KEY}=\r\n",
            ENV_LINES[3],
        ]
    )
    assert TOKEN not in after


def test_clear_is_idempotent_and_ignores_a_missing_file(tmp_path: Path) -> None:
    path = _env_file(tmp_path)
    clear_env_variable(path, TOKEN_ENV_KEY)
    first = path.read_bytes()

    assert clear_env_variable(path, TOKEN_ENV_KEY) is True
    assert path.read_bytes() == first
    assert clear_env_variable(tmp_path / "no-existe.env", TOKEN_ENV_KEY) is True


def test_clear_does_not_touch_a_similarly_named_variable(tmp_path: Path) -> None:
    lines = [f"X_{TOKEN_ENV_KEY}='valor'\n", f"# {TOKEN_ENV_KEY}='comentario'\n"]
    path = _env_file(tmp_path, lines)
    before = path.read_bytes()

    assert clear_env_variable(path, TOKEN_ENV_KEY) is True
    assert path.read_bytes() == before


def test_clear_only_logs_when_the_file_is_not_writable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _env_file(tmp_path)
    before = path.read_bytes()
    os.chmod(path, stat.S_IREAD)
    try:
        with caplog.at_level("WARNING"):
            assert clear_env_variable(path, TOKEN_ENV_KEY) is False
    finally:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)

    assert path.read_bytes() == before
    assert any("No se pudo escribir" in r.message for r in caplog.records)
    # El token nunca se loguea.
    assert all(TOKEN not in r.getMessage() for r in caplog.records)


# ── vinculación al arrancar ───────────────────────────────────────────────


async def test_token_is_redeemed_once_and_cleared_from_the_env(
    make_services: Callable[..., CloudLinkServices], with_token: Settings, tmp_path: Path
) -> None:
    api = FakeCloudApi()
    services = make_services(api, settings=with_token)
    env = _env_file(tmp_path)

    status = await link_from_settings(services, env_path=env)

    assert status == LinkStatus.LINKED
    assert [t for t, _ in api.enroll_calls] == [TOKEN]
    assert TOKEN not in env.read_text(encoding="utf-8")
    assert f"{TOKEN_ENV_KEY}=\r\n".encode() in env.read_bytes()
    state = await services.repository.get()
    assert state.status == LinkStatus.LINKED and state.client_code == "FARMX"


async def test_an_unwritable_env_does_not_undo_the_link(
    make_services: Callable[..., CloudLinkServices], with_token: Settings, tmp_path: Path
) -> None:
    api = FakeCloudApi()
    services = make_services(api, settings=with_token)
    env = _env_file(tmp_path)
    os.chmod(env, stat.S_IREAD)
    try:
        status = await link_from_settings(services, env_path=env)
    finally:
        os.chmod(env, stat.S_IWRITE | stat.S_IREAD)

    assert status == LinkStatus.LINKED
    assert (await services.repository.get()).status == LinkStatus.LINKED


async def test_an_invalid_token_leaves_the_error_and_is_not_retried_in_a_loop(
    make_services: Callable[..., CloudLinkServices],
    with_token: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeCloudApi(enroll_error=http_error(404, "enrollment_token_invalid"))
    services = make_services(api, settings=with_token)
    env = _env_file(tmp_path)
    before = env.read_bytes()
    monkeypatch.setattr(scheduler_module, "IDLE_POLL_SECONDS", 0.0)
    monkeypatch.setattr(scheduler_module, "MIN_WAIT_SECONDS", 0.01)

    # El scheduler real: varias vueltas de sus dos bucles.
    scheduler = CloudLinkScheduler(services, env_path=env)
    scheduler.start()
    await asyncio.sleep(0.3)
    await scheduler.stop()

    state = await services.repository.get()
    assert state.status == LinkStatus.UNLINKED
    assert state.last_error_code == "enrollment_token_invalid"
    assert len(api.enroll_calls) == 1, "no debe reintentar en bucle"
    assert env.read_bytes() == before, "un canje fallido no borra el token"


async def test_a_network_failure_is_recorded_and_not_retried(
    make_services: Callable[..., CloudLinkServices], with_token: Settings, tmp_path: Path
) -> None:
    api = FakeCloudApi(enroll_error=net_error())
    services = make_services(api, settings=with_token)

    assert await link_from_settings(services, env_path=_env_file(tmp_path)) is None

    assert len(api.enroll_calls) == 1
    assert (await services.repository.get()).last_error_code == "network_error"


async def test_nothing_happens_without_token_or_url(
    make_services: Callable[..., CloudLinkServices],
    make_settings: Callable[..., Settings],
    tmp_path: Path,
) -> None:
    api = FakeCloudApi()
    no_token = make_services(api, settings=make_settings())
    no_url = make_services(
        api, settings=make_settings(savi_cloud_enrollment_token=TOKEN, savi_cloud_url="")
    )

    assert await link_from_settings(no_token, env_path=_env_file(tmp_path)) is None
    assert await link_from_settings(no_url, env_path=_env_file(tmp_path)) is None
    assert api.enroll_calls == []


async def test_an_already_linked_installation_only_cleans_the_leftover_token(
    make_services: Callable[..., CloudLinkServices], with_token: Settings, tmp_path: Path
) -> None:
    api = FakeCloudApi()
    services = make_services(api, settings=with_token)
    await services.link.execute(cloud_url=CLOUD_URL, token="otro")
    api.enroll_calls.clear()
    env = _env_file(tmp_path)

    status = await link_from_settings(services, env_path=env)

    assert status == LinkStatus.LINKED
    assert api.enroll_calls == []
    assert TOKEN not in env.read_text(encoding="utf-8")
