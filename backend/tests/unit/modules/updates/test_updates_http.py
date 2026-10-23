"""Endpoints `/updates` y el armado del coordinador según la instalación."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

import app.main as main_module
import app.modules.updates.infrastructure.provider as provider
from app.infrastructure.config import Settings, get_settings
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import get_current_user
from app.modules.updates.application.coordinator import UpdateCoordinator
from app.modules.updates.domain.value_objects import ReleaseVersion
from app.modules.updates.infrastructure.launcher import installed_per_machine, silent_parameters
from tests.unit.modules.updates.test_coordinator import (
    FakeDownloader,
    FakeHistory,
    FakeLauncher,
    FakeResults,
    FakeSource,
    FakeTurns,
    _manifest,
)

_USER = AuthenticatedUser(
    id=7,
    login="AGENTE",
    full_name="Agente",
    is_admin=False,
    is_active=True,
)


@pytest.fixture
def launcher() -> FakeLauncher:
    return FakeLauncher()


@pytest.fixture
def coordinator(launcher: FakeLauncher) -> Iterator[UpdateCoordinator]:
    coordinator = UpdateCoordinator(
        current=ReleaseVersion.parse("v1.3.2"),
        source=FakeSource(_manifest()),
        downloader=FakeDownloader(),
        launcher=launcher,
        results=FakeResults(launcher),
        history=FakeHistory(),
        turns=FakeTurns(),
    )
    provider._coordinator = coordinator  # pyright: ignore[reportPrivateUsage]
    yield coordinator
    provider._coordinator = None  # pyright: ignore[reportPrivateUsage]


def _client(host: str = "127.0.0.1") -> TestClient:
    get_settings.cache_clear()
    app = main_module.create_app()
    app.dependency_overrides[get_current_user] = lambda: _USER
    return TestClient(app, client=(host, 50000))  # sin `with`: no corre el lifespan


def test_status_is_disabled_without_a_coordinator() -> None:
    body = _client().get("/updates/status").json()
    assert body["enabled"] is False


async def test_status_reports_the_published_version(coordinator: UpdateCoordinator) -> None:
    await coordinator.check()
    body = _client().get("/updates/status").json()
    assert body["enabled"] is True
    assert body["state"] == "recommended"
    assert body["current_version"] == "v1.3.2"
    assert body["available_version"] == "v1.4.0"
    assert body["can_apply"] is True


async def test_remote_clients_cannot_apply(
    coordinator: UpdateCoordinator, launcher: FakeLauncher
) -> None:
    await coordinator.check()
    client = _client("192.168.1.20")
    assert client.get("/updates/status").json()["can_apply"] is False

    response = client.post("/updates/apply")
    assert response.status_code == 403
    assert "área de sistemas" in response.json()["detail"]
    assert launcher.launched == []


async def test_local_apply_starts_in_the_background(coordinator: UpdateCoordinator) -> None:
    await coordinator.check()
    response = _client().post("/updates/apply")
    assert response.status_code == 202
    assert response.json()["phase"] == "downloading"


def test_apply_without_updates_is_rejected() -> None:
    assert _client().post("/updates/apply").status_code == 400


# --------------------------------------------------------------- armado


def _public_key() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def _settings(**values: object) -> Settings:
    return Settings.model_validate({"agent_db_engine": "sqlite", **values})


@pytest.mark.parametrize("version", ["0.0.0-dev", "v1.3.2-4-gabc1234", "v1.3.2-sucio"])
def test_development_builds_do_not_check(version: str) -> None:
    settings = _settings(update_url="https://updates.example.com/savi")
    assert (
        provider.build_coordinator(settings, version=version, public_key_b64=_public_key()) is None
    )


def test_without_url_or_key_updates_stay_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider, "DEFAULT_UPDATE_URL", "")
    assert (
        provider.build_coordinator(_settings(), version="v1.3.2", public_key_b64=_public_key())
        is None
    )
    with_url = _settings(update_url="https://updates.example.com/savi")
    assert provider.build_coordinator(with_url, version="v1.3.2", public_key_b64="") is None


def test_env_url_overrides_the_official_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider, "DEFAULT_UPDATE_URL", "https://updates.example.com/savi")
    assert provider.update_url(_settings()) == "https://updates.example.com/savi"
    local = _settings(update_url="http://127.0.0.1:8765/savi")
    assert provider.update_url(local) == "http://127.0.0.1:8765/savi"


def test_released_build_with_url_and_key_checks() -> None:
    settings = _settings(update_url="https://updates.example.com/savi", update_channel="beta")
    coordinator = provider.build_coordinator(
        settings, version="v1.3.2", public_key_b64=_public_key()
    )
    assert coordinator is not None
    assert coordinator.current == ReleaseVersion(1, 3, 2)


def test_program_files_install_needs_elevation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    assert installed_per_machine(tmp_path / "Program Files" / "SAVI" / "SAVI.exe")
    assert not installed_per_machine(
        tmp_path / "AppData" / "Local" / "Programs" / "SAVI" / "SAVI.exe"
    )


def test_installer_runs_silently_and_closes_savi() -> None:
    params = silent_parameters(Path("C:/datos/install.log"))
    for flag in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"):
        assert flag in params
    assert '/LOG="' in params
