"""Publicación de una versión de SAVI en el servidor de actualizaciones.

Spec: `docs/plataforma/09-actualizacion-automatica.md`, sección 7. Publicar es
una decisión humana, igual que crear el tag: este script no corre en CI.

Necesita `cryptography` y el dominio del backend para validar lo que arma,
así que se corre con el entorno del backend (desde la raíz del monorepo):

    uv run --project backend python scripts/publish-release.py keygen --out <ruta>
    uv run --project backend python scripts/publish-release.py build \
        --installer installer/output/SAVI-Setup-v1.4.0.exe \
        --base-url https://updates.<dominio-seo>/savi --key <ruta> [--channel beta]
    uv run --project backend python scripts/publish-release.py promote   # solo versiones finales
    uv run --project backend python scripts/publish-release.py upload \
        --host savi-publish@<servidor> --remote-dir /srv/savi-master/updates/savi
    uv run --project backend python scripts/publish-release.py verify \
        --base-url https://updates.<dominio-seo>/savi --channel stable

`build` deja todo en una carpeta local (`installer/output/updates/` por
defecto), que es un espejo de lo que se sirve:

    stable.json  stable.json.sig  beta.json  beta.json.sig  releases/SAVI-Setup-vX.Y.Z.exe

Así se puede probar en local sirviendo esa carpeta con `python -m http.server`
antes de subir nada.

Las candidatas (`SAVI-Setup-v1.4.0-rc.1.exe`) solo se publican en `beta`: `build
--channel stable` y `promote` las rechazan.

La clave privada Ed25519 vive fuera del repositorio, en el equipo de
publicación. La pública va incrustada en SAVI
(`backend/app/modules/updates/infrastructure/trust.py`).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.updates.domain.exceptions import UpdateError  # noqa: E402
from app.modules.updates.domain.value_objects import (  # noqa: E402
    ReleaseManifest,
    ReleaseVersion,
)
from app.modules.updates.infrastructure.http_source import (  # noqa: E402
    HttpInstallerDownloader,
    HttpManifestSource,
)
from app.modules.updates.infrastructure.signing import (  # noqa: E402
    load_public_keys,
    verify_manifest,
)
from app.modules.updates.infrastructure.trust import UPDATE_PUBLIC_KEYS  # noqa: E402

DEFAULT_OUT = ROOT / "installer" / "output" / "updates"
CHANNELS = ("stable", "beta")
# Plazo por defecto de una actualización obligatoria (D4).
DEFAULT_WINDOW = timedelta(hours=72)
NO_MINIMUM = "v0.0.0"
_INSTALLER_NAME = re.compile(r"^SAVI-Setup-(v\d+\.\d+\.\d+(?:-rc\.[1-9]\d*)?)\.exe$")
_CANDIDATE_IN_STABLE = (
    "{version} es una candidata (-rc): se prueba en beta y no pasa a stable. "
    "Para stable se compila la versión final."
)


class PublishError(Exception):
    pass


@dataclass(frozen=True)
class Minimum:
    version: str
    since: datetime


# ------------------------------------------------------------------ claves


def keygen(out: Path) -> str:
    """Crea la clave privada en `out` y devuelve la pública en base64."""
    out = out.resolve()
    if out.is_relative_to(ROOT):
        raise PublishError("La clave privada no puede quedar dentro del repositorio.")
    if out.exists():
        raise PublishError(f"{out} ya existe: no se pisa una clave.")
    key = Ed25519PrivateKey.generate()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return public_key_b64(key)


def public_key_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def load_key(path: Path) -> Ed25519PrivateKey:
    key = load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise PublishError(f"{path} no es una clave Ed25519.")
    return key


# -------------------------------------------------------------- manifiesto


def installer_version(installer: Path) -> str:
    """La versión sale del nombre que pone `build.ps1`.

    Un build con cambios sin commitear se llama `SAVI-Setup-v1.4.0-sucio.exe`
    (o con el commit) y no calza con el patrón: no se publica.
    """
    match = _INSTALLER_NAME.match(installer.name)
    if match is None:
        raise PublishError(
            f"{installer.name} no es un instalador de una versión publicada "
            "(SAVI-Setup-vX.Y.Z[-rc.N].exe). Un build sucio no se publica."
        )
    return match[1]


def tag_notes(version: str) -> str:
    """Las notas del tag anotado, sin la primera línea (que repite la versión)."""
    result = subprocess.run(
        ["git", "tag", "-l", "--format=%(contents)", version],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise PublishError(f"No existe el tag {version}: primero se crea con scripts/version.py.")
    return "\n".join(lines[1:]).strip()


def _previous(out: Path, channel: str) -> dict[str, object] | None:
    path = out / f"{channel}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def previous_minimum(out: Path, channel: str) -> Minimum | None:
    data = _previous(out, channel)
    if data is None:
        return None
    return Minimum(str(data["min_version"]), datetime.fromisoformat(str(data["min_version_from"])))


def reject_older_than_published(out: Path, channel: str, version: str) -> None:
    """Un canal nunca retrocede. Volver a publicar la misma versión sí se
    permite (por ejemplo, para corregir las notas)."""
    data = _previous(out, channel)
    if data is None:
        return
    published = str(data["version"])
    if ReleaseVersion.parse(version) < ReleaseVersion.parse(published):
        raise PublishError(
            f"{channel} ya publica {published}: no se publica una versión anterior ({version}). "
            "Para corregir, se publica una versión nueva."
        )


def resolve_minimum(
    *,
    requested: str | None,
    requested_from: str | None,
    previous: Minimum | None,
    now: datetime,
) -> Minimum:
    """`min_version` se mantiene salvo que se pida otro.

    Cuando cambia, el plazo es de 72 h, o inmediato con `--min-version-from now`.
    """
    if requested is None:
        if requested_from is not None:
            raise PublishError("--min-version-from va junto con --min-version.")
        return previous or Minimum(NO_MINIMUM, now)
    if requested_from is None:
        since = now + DEFAULT_WINDOW
    elif requested_from == "now":
        since = now
    else:
        since = datetime.fromisoformat(requested_from)
        if since.tzinfo is None:
            raise PublishError("--min-version-from tiene que indicar la zona horaria.")
    return Minimum(requested, since)


def build_manifest(
    *,
    version: str,
    installer: Path,
    base_url: str,
    minimum: Minimum,
    notes: str,
    now: datetime,
) -> bytes:
    digest = hashlib.sha256()
    with installer.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    data = {
        "version": version,
        "published_at": _iso(now),
        "url": f"{base_url.rstrip('/')}/releases/{installer.name}",
        "sha256": digest.hexdigest(),
        "size": installer.stat().st_size,
        "min_version": minimum.version,
        "min_version_from": _iso(minimum.since),
        "notes": notes,
    }
    # Se valida con el mismo dominio que lo va a leer cada SAVI: un
    # manifiesto que la aplicación rechazaría no sale de acá.
    ReleaseManifest.from_mapping(data)
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def sign(key: Ed25519PrivateKey, payload: bytes) -> bytes:
    signature = base64.b64encode(key.sign(payload)) + b"\n"
    # Se verifica con el código de la aplicación, no con el de este script.
    public = load_public_keys([public_key_b64(key)])
    verify_manifest(public, payload, signature)
    return signature


def build(
    *,
    installer: Path,
    base_url: str,
    key: Ed25519PrivateKey,
    channel: str,
    out: Path,
    min_version: str | None,
    min_version_from: str | None,
    notes: str | None,
    now: datetime,
) -> Path:
    version = installer_version(installer)
    if channel == "stable" and ReleaseVersion.parse(version).is_candidate:
        raise PublishError(_CANDIDATE_IN_STABLE.format(version=version))
    reject_older_than_published(out, channel, version)
    minimum = resolve_minimum(
        requested=min_version,
        requested_from=min_version_from,
        previous=previous_minimum(out, channel),
        now=now,
    )
    payload = build_manifest(
        version=version,
        installer=installer,
        base_url=base_url,
        minimum=minimum,
        notes=tag_notes(version) if notes is None else notes,
        now=now,
    )
    releases = out / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    if installer.resolve() != (releases / installer.name).resolve():
        shutil.copy2(installer, releases / installer.name)
    (out / f"{channel}.json").write_bytes(payload)
    (out / f"{channel}.json.sig").write_bytes(sign(key, payload))
    return out / f"{channel}.json"


def promote(out: Path) -> None:
    """Pasa `beta` a `stable` tal cual: el manifiesto no nombra el canal, así
    que la misma firma vale para los dos. Una candidata no se promueve."""
    beta = _previous(out, "beta")
    if beta is not None:
        if ReleaseVersion.parse(str(beta["version"])).is_candidate:
            raise PublishError(_CANDIDATE_IN_STABLE.format(version=beta["version"]))
        # Igual que `build`: un canal nunca retrocede.
        reject_older_than_published(out, "stable", str(beta["version"]))
    for suffix in (".json", ".json.sig"):
        source = out / f"beta{suffix}"
        if not source.is_file():
            raise PublishError(f"No hay {source.name} para promover.")
        shutil.copy2(source, out / f"stable{suffix}")


# --------------------------------------------------------------- verificación


def verify(*, base_url: str, channel: str, public_keys_b64: list[str]) -> ReleaseManifest:
    """Lo que haría una instalación: lee el manifiesto publicado, verifica la
    firma, descarga el instalador y verifica su SHA-256.

    Con el mismo código del backend: si esto pasa, SAVI lo acepta.
    """
    public_keys = load_public_keys(public_keys_b64)
    if not public_keys:
        raise PublishError("No hay clave pública: pásela con --public-key o péguela en trust.py.")

    async def run() -> ReleaseManifest:
        source = HttpManifestSource(base_url=base_url, channel=channel, public_keys=public_keys)
        manifest = await source.fetch()
        with tempfile.TemporaryDirectory() as folder:
            downloader = HttpInstallerDownloader(target_dir=Path(folder))
            await downloader.download(manifest, lambda _: None)
        return manifest

    return asyncio.run(run())


# ------------------------------------------------------------------- subida


def upload_commands(
    *, out: Path, channel: str, host: str, remote_dir: str, identity: Path | None
) -> list[list[str]]:
    """Comandos en orden: primero el instalador, al final el manifiesto.

    El manifiesto se sube con otro nombre y se renombra al final. Así ningún
    equipo lee uno a medio escribir ni uno que apunte a un `.exe` que todavía
    no está.
    """
    data = json.loads((out / f"{channel}.json").read_text(encoding="utf-8"))
    installer = out / "releases" / str(data["url"]).rsplit("/", 1)[-1]
    if not installer.is_file():
        raise PublishError(f"Falta {installer}: primero se corre build.")
    ssh_opts = ["-i", str(identity)] if identity is not None else []
    remote = remote_dir.rstrip("/")
    manifest, signature = f"{remote}/{channel}.json", f"{remote}/{channel}.json.sig"
    return [
        ["ssh", *ssh_opts, host, f"mkdir -p '{remote}/releases'"],
        ["scp", *ssh_opts, str(installer), f"{host}:{remote}/releases/{installer.name}"],
        ["scp", *ssh_opts, str(out / f"{channel}.json.sig"), f"{host}:{signature}.tmp"],
        ["scp", *ssh_opts, str(out / f"{channel}.json"), f"{host}:{manifest}.tmp"],
        [
            "ssh",
            *ssh_opts,
            host,
            f"mv '{signature}.tmp' '{signature}' && mv '{manifest}.tmp' '{manifest}'",
        ],
    ]


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="command", required=True)

    p_keygen = sub.add_parser("keygen", help="crea el par de claves Ed25519")
    p_keygen.add_argument("--out", type=Path, required=True, help="ruta de la clave privada")

    p_build = sub.add_parser("build", help="arma y firma el manifiesto en la carpeta local")
    p_build.add_argument("--installer", type=Path, required=True)
    p_build.add_argument("--base-url", required=True, help="https://updates.<dominio>/savi")
    p_build.add_argument("--key", type=Path, required=True, help="clave privada Ed25519")
    p_build.add_argument("--channel", choices=CHANNELS, default="beta")
    p_build.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p_build.add_argument("--min-version", help="vX.Y.Z que toda instalación debe alcanzar")
    p_build.add_argument("--min-version-from", help="'now' o fecha ISO con zona (default +72 h)")
    p_build.add_argument("--notes", help="texto para el usuario; por defecto, las notas del tag")

    p_promote = sub.add_parser("promote", help="pasa beta a stable")
    p_promote.add_argument("--out", type=Path, default=DEFAULT_OUT)

    p_upload = sub.add_parser("upload", help="sube un canal al servidor por SSH")
    p_upload.add_argument("--host", required=True, help="usuario@servidor")
    p_upload.add_argument("--remote-dir", required=True)
    p_upload.add_argument("--channel", choices=CHANNELS, default="beta")
    p_upload.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p_upload.add_argument("--identity", type=Path, help="llave SSH de savi-publish")
    p_upload.add_argument("--dry-run", action="store_true", help="solo muestra los comandos")

    p_verify = sub.add_parser("verify", help="verifica lo publicado como lo haría SAVI")
    p_verify.add_argument("--base-url", required=True)
    p_verify.add_argument("--channel", choices=CHANNELS, default="stable")
    p_verify.add_argument(
        "--public-key",
        action="append",
        help="puede repetirse; por defecto, las de trust.py",
    )

    args = parser.parse_args(argv)

    # Igual que `version.py`: Windows abre la consola en cp1252 y los mensajes
    # llevan acentos.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    try:
        if args.command == "keygen":
            public = keygen(args.out)
            print(f"Clave privada: {args.out.resolve()}  (guárdela fuera del repositorio)")
            print(f"Clave pública (va en trust.py): {public}")
        elif args.command == "build":
            path = build(
                installer=args.installer,
                base_url=args.base_url,
                key=load_key(args.key),
                channel=args.channel,
                out=args.out,
                min_version=args.min_version,
                min_version_from=args.min_version_from,
                notes=args.notes,
                now=datetime.now(UTC),
            )
            print(path.read_text(encoding="utf-8"))
            print(f"Listo en {args.out.resolve()}. Pruebe en local antes de subir.")
        elif args.command == "promote":
            promote(args.out)
            print("beta pasó a stable.")
        elif args.command == "verify":
            manifest = verify(
                base_url=args.base_url,
                channel=args.channel,
                public_keys_b64=args.public_key or list(UPDATE_PUBLIC_KEYS),
            )
            print(
                f"{args.channel}: {manifest.version} (mínima {manifest.min_version} desde "
                f"{_iso(manifest.min_version_from)}). Firma y SHA-256 verificados."
            )
        else:
            commands = upload_commands(
                out=args.out,
                channel=args.channel,
                host=args.host,
                remote_dir=args.remote_dir,
                identity=args.identity,
            )
            for command in commands:
                print(" ".join(command))
                if not args.dry_run:
                    subprocess.run(command, check=True)
    except (PublishError, UpdateError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
