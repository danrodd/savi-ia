"""`scripts/publish-release.py`: lo que arma tiene que aceptarlo SAVI tal cual.

El script valida y verifica con el código del backend, así que estos tests
cubren el acuerdo entre quien publica y quien actualiza.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.modules.updates.domain.exceptions import InvalidManifestError
from app.modules.updates.domain.value_objects import ReleaseVersion
from app.modules.updates.infrastructure.signing import (
    load_public_keys,
    verify_installer,
    verify_manifest,
)

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "publish-release.py"
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_publish_release_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def installer(tmp_path: Path) -> Path:
    path = tmp_path / "SAVI-Setup-v1.4.0.exe"
    path.write_bytes(b"MZ" + b"\x00" * 4096)
    return path


def _build(key: Ed25519PrivateKey, installer: Path, out: Path, **kwargs: object) -> Path:
    params: dict[str, object] = {
        "installer": installer,
        "base_url": "https://updates.example.com/savi/",
        "key": key,
        "channel": "beta",
        "out": out,
        "min_version": None,
        "min_version_from": None,
        "notes": "Corrige la pantalla en blanco.",
        "now": NOW,
    }
    params.update(kwargs)
    return script.build(**params)


def test_built_manifest_verifies_with_the_app(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    manifest_path = _build(key, installer, out)

    public = load_public_keys([script.public_key_b64(key)])
    manifest = verify_manifest(
        public, manifest_path.read_bytes(), (out / "beta.json.sig").read_bytes()
    )
    assert manifest.version == ReleaseVersion(1, 4, 0)
    assert manifest.url == "https://updates.example.com/savi/releases/SAVI-Setup-v1.4.0.exe"
    verify_installer(out / "releases" / installer.name, manifest)


def test_a_server_move_is_announced_in_the_signed_manifest(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    manifest_path = _build(key, installer, out, update_url="https://new.example.com/savi/")

    public = load_public_keys([script.public_key_b64(key)])
    manifest = verify_manifest(
        public, manifest_path.read_bytes(), (out / "beta.json.sig").read_bytes()
    )
    assert manifest.server_url == "https://new.example.com/savi"


def test_the_server_move_is_not_inherited_by_the_next_publication(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, installer, out, update_url="https://new.example.com/savi")
    data = script.json.loads(_build(key, installer, out).read_text(encoding="utf-8"))
    assert "update_url" not in data


def test_a_server_move_without_https_is_not_published(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    with pytest.raises(InvalidManifestError):
        _build(key, installer, tmp_path / "updates", update_url="http://new.example.com/savi")


def test_first_publication_has_no_minimum(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    data = script.json.loads(_build(key, installer, out).read_text(encoding="utf-8"))
    assert data["min_version"] == "v0.0.0"


def test_new_minimum_defaults_to_a_72_hour_window(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    path = _build(key, installer, out, min_version="v1.4.0")
    data = script.json.loads(path.read_text(encoding="utf-8"))
    assert data["min_version_from"] == "2026-11-05T15:00:00Z"


def test_minimum_can_be_immediate(key: Ed25519PrivateKey, installer: Path, tmp_path: Path) -> None:
    out = tmp_path / "updates"
    path = _build(key, installer, out, min_version="v1.4.0", min_version_from="now")
    data = script.json.loads(path.read_text(encoding="utf-8"))
    assert data["min_version_from"] == "2026-11-02T15:00:00Z"


def test_minimum_carries_over_from_the_previous_manifest(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, installer, out, min_version="v1.4.0", min_version_from="now")

    nxt = tmp_path / "SAVI-Setup-v1.4.1.exe"
    nxt.write_bytes(b"MZ" + b"\x01" * 4096)
    later = NOW + timedelta(days=10)
    data = script.json.loads(_build(key, nxt, out, now=later).read_text(encoding="utf-8"))
    assert data["min_version"] == "v1.4.0"
    assert data["min_version_from"] == "2026-11-02T15:00:00Z"


@pytest.mark.parametrize(
    "name", ["SAVI-Setup-v1.4.0-sucio.exe", "SAVI-Setup-v1.4.0-3-gabc1234.exe", "otro.exe"]
)
def test_dirty_or_unknown_builds_are_not_published(tmp_path: Path, name: str) -> None:
    with pytest.raises(script.PublishError):
        script.installer_version(tmp_path / name)


def test_minimum_above_the_version_is_rejected(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    with pytest.raises(Exception, match="min_version"):
        _build(key, installer, tmp_path / "updates", min_version="v2.0.0")


def test_a_channel_never_goes_back_to_an_older_version(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, installer, out)
    older = tmp_path / "SAVI-Setup-v1.3.9.exe"
    older.write_bytes(b"MZ" + b"\x02" * 4096)
    with pytest.raises(script.PublishError, match="versión anterior"):
        _build(key, older, out)
    # La misma versión sí se puede volver a publicar (por ejemplo, otras notas).
    _build(key, installer, out, notes="Notas corregidas.")


def test_promote_copies_beta_to_stable(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, installer, out)
    script.promote(out)
    assert (out / "stable.json").read_bytes() == (out / "beta.json").read_bytes()
    assert (out / "stable.json.sig").read_bytes() == (out / "beta.json.sig").read_bytes()


def test_upload_sends_the_installer_first_and_renames_the_manifest_last(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, installer, out)
    commands = script.upload_commands(
        out=out, channel="beta", host="savi-publish@srv", remote_dir="/srv/u/savi", identity=None
    )
    flat = [" ".join(c) for c in commands]
    assert "releases/SAVI-Setup-v1.4.0.exe" in flat[1]
    assert flat[-1].endswith("mv '/srv/u/savi/beta.json.tmp' '/srv/u/savi/beta.json'")
    assert all("beta.json" not in c for c in flat[:2])


def test_keygen_refuses_a_path_inside_the_repository() -> None:
    with pytest.raises(script.PublishError):
        script.keygen(script.ROOT / "clave.pem")


def test_keygen_writes_a_loadable_key(tmp_path: Path) -> None:
    path = tmp_path / "claves" / "savi-updates.pem"
    public = script.keygen(path)
    assert script.public_key_b64(script.load_key(path)) == public
    with pytest.raises(script.PublishError):
        script.keygen(path)


# ---------------------------------------------------------------- candidatas


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    path = tmp_path / "SAVI-Setup-v1.4.0-rc.1.exe"
    path.write_bytes(b"MZ" + b"\x03" * 4096)
    return path


def test_a_candidate_installer_name_is_a_publishable_version(candidate: Path) -> None:
    assert script.installer_version(candidate) == "v1.4.0-rc.1"


def test_a_candidate_is_published_in_beta_and_the_app_accepts_it(
    key: Ed25519PrivateKey, candidate: Path, tmp_path: Path
) -> None:
    manifest_path = _build(key, candidate, tmp_path / "updates", channel="beta")

    assert json.loads(manifest_path.read_text(encoding="utf-8"))["version"] == "v1.4.0-rc.1"


def test_a_candidate_is_not_published_in_stable(
    key: Ed25519PrivateKey, candidate: Path, tmp_path: Path
) -> None:
    with pytest.raises(script.PublishError, match="candidata"):
        _build(key, candidate, tmp_path / "updates", channel="stable")


def test_a_candidate_is_not_promoted_to_stable(
    key: Ed25519PrivateKey, candidate: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, candidate, out, channel="beta")

    with pytest.raises(script.PublishError, match="candidata"):
        script.promote(out)
    assert not (out / "stable.json").exists()


def test_candidates_go_up_in_beta_and_the_final_replaces_them(
    key: Ed25519PrivateKey, candidate: Path, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    _build(key, candidate, out)
    second = tmp_path / "SAVI-Setup-v1.4.0-rc.2.exe"
    second.write_bytes(b"MZ" + b"\x04" * 4096)
    _build(key, second, out)

    # La candidata anterior no vuelve, pero la final sí puede publicarse encima.
    with pytest.raises(script.PublishError, match="versión anterior"):
        _build(key, candidate, out)
    _build(key, installer, out)
    script.promote(out)
    assert json.loads((out / "stable.json").read_text(encoding="utf-8"))["version"] == "v1.4.0"


def test_promote_does_not_take_stable_back_to_an_older_version(
    key: Ed25519PrivateKey, installer: Path, tmp_path: Path
) -> None:
    out = tmp_path / "updates"
    newer = tmp_path / "SAVI-Setup-v1.5.0.exe"
    newer.write_bytes(b"MZ" + b"\x05" * 4096)
    _build(key, newer, out, channel="stable")
    _build(key, installer, out, channel="beta")

    with pytest.raises(script.PublishError, match="versión anterior"):
        script.promote(out)
    assert json.loads((out / "stable.json").read_text(encoding="utf-8"))["version"] == "v1.5.0"
