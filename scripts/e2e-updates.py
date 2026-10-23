"""Prueba de punta a punta en local: publicar, servir por HTTP y actualizar.

Usa el script de publicación real, un servidor HTTP real y el coordinador real
del backend. Solo el lanzamiento del instalador es falso: el .exe de prueba no
es un instalador. No toca la red ni el servidor de pruebas.

    uv run --project backend python scripts/e2e-updates.py

Sale con 0 si pasan todos los controles. Trabaja en una carpeta temporal.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = Path(tempfile.gettempdir()) / "savi-e2e-updates"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}/savi"

sys.path.insert(0, str(REPO / "backend"))

from app.infrastructure.config import Settings  # noqa: E402
from app.modules.updates.application.coordinator import ApplyPhase  # noqa: E402
from app.modules.updates.domain.interfaces import InstallerLauncher  # noqa: E402
from app.modules.updates.infrastructure import provider  # noqa: E402


class RecordingLauncher(InstallerLauncher):
    def __init__(self) -> None:
        self.launched: list[Path] = []

    def launch(self, installer: Path) -> None:
        self.launched.append(installer)


def publish(version: str, content: bytes, *extra: str) -> None:
    installer = WORK / "builds" / f"SAVI-Setup-{version}.exe"
    installer.parent.mkdir(parents=True, exist_ok=True)
    installer.write_bytes(content)
    subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "publish-release.py"),
            "build",
            "--installer",
            str(installer),
            "--base-url",
            BASE,
            "--key",
            str(WORK / "key.pem"),
            "--channel",
            "stable",
            "--out",
            str(WORK / "srv" / "savi"),
            "--notes",
            f"Notas de {version}.",
            *extra,
        ],
        check=True,
        capture_output=True,
    )


def run_verify(public_key: str) -> subprocess.CompletedProcess[bytes]:
    """El comando `verify` del script, como se usa contra el servidor real."""
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "publish-release.py"),
            "verify",
            "--base-url",
            BASE,
            "--channel",
            "stable",
            "--public-key",
            public_key,
        ],
        capture_output=True,
        check=False,
    )


def coordinator(public_key: str, launcher: RecordingLauncher) -> provider.UpdateCoordinator:
    settings = Settings.model_validate({"agent_db_engine": "sqlite", "update_url": BASE})
    built = provider.build_coordinator(settings, version="v1.3.2", public_key_b64=public_key)
    assert built is not None
    built._launcher = launcher  # noqa: SLF001
    built._downloader._target_dir = WORK / "downloads"  # noqa: SLF001
    return built


async def run(public_key: str) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))

    payload = b"MZ" + bytes(range(256)) * 4096  # ~1 MB

    # 1. Versión recomendada: detecta, descarga, verifica y lanza.
    publish("v1.4.0", payload)
    launcher = RecordingLauncher()
    c = coordinator(public_key, launcher)
    await c.check()
    snap = c.snapshot()
    record("detecta v1.4.0 recomendada", snap.decision.state == "recommended", snap.decision.state)
    await c.start_apply()
    snap = c.snapshot()
    ok = snap.phase is ApplyPhase.INSTALLING and len(launcher.launched) == 1
    record("descarga, verifica y lanza", ok, f"{snap.phase} {launcher.launched}")
    downloaded = launcher.launched[0].read_bytes() if launcher.launched else b""
    record("el archivo lanzado es el publicado", downloaded == payload, f"{len(downloaded)} bytes")

    # 1b. El comando `verify` del script, como se usará contra el servidor real.
    verify = run_verify(public_key)
    out = verify.stdout.decode("utf-8", "replace").strip()
    record("verify confirma lo publicado", verify.returncode == 0 and "verificados" in out, out)

    # 2. Instalador cambiado en el servidor después de publicar.
    exe = WORK / "srv" / "savi" / "releases" / "SAVI-Setup-v1.4.0.exe"
    tampered = payload[:-1] + b"\x00"
    assert tampered != payload and len(tampered) == len(payload)
    exe.write_bytes(tampered)
    launcher = RecordingLauncher()
    c = coordinator(public_key, launcher)
    await c.check()
    await c.start_apply()
    snap = c.snapshot()
    ok = snap.phase is ApplyPhase.FAILED and not launcher.launched
    record("rechaza un instalador cambiado", ok, f"{snap.phase}: {snap.apply_error}")
    verify = run_verify(public_key)
    err = verify.stderr.decode("utf-8", "replace").strip()
    record("verify detecta el instalador cambiado", verify.returncode == 1, err)
    exe.write_bytes(payload)

    # 3. Manifiesto cambiado en el servidor (sin poder re-firmarlo).
    manifest_path = WORK / "srv" / "savi" / "stable.json"
    original = manifest_path.read_bytes()
    data = json.loads(original)
    data["url"] = f"{BASE}/releases/otro.exe"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    c = coordinator(public_key, RecordingLauncher())
    await c.check()
    snap = c.snapshot()
    record(
        "ignora un manifiesto sin firma válida",
        snap.decision.state == "up_to_date" and snap.checked_at is None,
        str(snap.decision.state),
    )
    manifest_path.write_bytes(original)

    # 4. Obligatoria inmediata: bloquea.
    publish("v1.4.1", payload + b"1", "--min-version", "v1.4.1", "--min-version-from", "now")
    c = coordinator(public_key, RecordingLauncher())
    await c.check()
    snap = c.snapshot()
    record("min_version inmediata bloquea", snap.decision.state == "blocked", snap.decision.state)

    # 5. Obligatoria con plazo por defecto (72 h).
    publish("v1.4.2", payload + b"2", "--min-version", "v1.4.2")
    c = coordinator(public_key, RecordingLauncher())
    await c.check()
    snap = c.snapshot()
    deadline = snap.decision.deadline
    record(
        "min_version con plazo avisa con fecha",
        snap.decision.state == "required" and deadline is not None,
        f"{snap.decision.state} hasta {deadline}",
    )

    # 6a. El script se niega a publicar una versión anterior en el canal.
    try:
        publish("v1.3.0", payload + b"3")
        record("el script no publica una versión anterior", False, "publicó")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "replace").strip()
        record("el script no publica una versión anterior", "anterior" in stderr, stderr)

    # 6b. Aunque alguien firme y suba un manifiesto viejo, SAVI no baja.
    import base64

    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    key = load_pem_private_key((WORK / "key.pem").read_bytes(), password=None)
    old = json.loads(manifest_path.read_text(encoding="utf-8"))
    old.update({"version": "v1.3.0", "min_version": "v0.0.0"})
    old_bytes = json.dumps(old).encode()
    manifest_path.write_bytes(old_bytes)
    (manifest_path.parent / "stable.json.sig").write_bytes(base64.b64encode(key.sign(old_bytes)))  # type: ignore[union-attr, call-arg]
    c = coordinator(public_key, RecordingLauncher())
    await c.check()
    snap = c.snapshot()
    record("no ofrece bajar de versión", snap.decision.state == "up_to_date", snap.decision.state)

    return results


def main() -> int:
    import shutil

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    keygen = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "publish-release.py"),
            "keygen",
            "--out",
            str(WORK / "key.pem"),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    public_key = keygen.stdout.strip().rsplit(" ", 1)[-1]

    (WORK / "srv" / "savi").mkdir(parents=True)
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(PORT),
            "--bind",
            "127.0.0.1",
            "--directory",
            str(WORK / "srv"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.5)
        results = asyncio.run(run(public_key))
    finally:
        server.terminate()
        server.wait(timeout=10)

    failed = 0
    for name, ok, detail in results:
        failed += not ok
        print(f"{'OK  ' if ok else 'FALLA'} {name}  ({detail})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
