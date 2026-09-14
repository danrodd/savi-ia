#!/usr/bin/env python3
"""Sube la versión de SAVI en todo el monorepo desde un único comando.

`backend/app/_version.py` es la fuente única (ver
`installer/README.md#versionado`). Este script:

1. Valida que la nueva versión sea SemVer y mayor que la actual.
2. La escribe en `backend/app/_version.py`.
3. Replica el mismo número en `frontend/package.json` (cosmético — nada
   lo lee en runtime, pero evita que quede un `0.0.0` mintiendo si
   alguna vez se publica el paquete o se inspecciona con `npm ls`).
4. Antepone una sección nueva a `CHANGELOG.md` (formato Keep a
   Changelog) para completar a mano antes de commitear.

NO toca `installer/savi.iss`: `build.ps1` lee la versión de
`_version.py` en el momento de compilar, así que ese archivo no
necesita bumpearse nunca.

NO crea el commit ni el tag — son decisiones del usuario. Al terminar,
sugiere los dos comandos.

Uso:
    uv run python installer/bump_version.py 0.2.0
    (o: python installer/bump_version.py 0.2.0 — no tiene dependencias
    fuera de la stdlib)
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "backend" / "app" / "_version.py"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
CHANGELOG = ROOT / "CHANGELOG.md"


def _parse(version: str) -> tuple[int, int, int]:
    match = _SEMVER.match(version)
    if not match:
        raise SystemExit(
            f"'{version}' no es SemVer válido (esperado MAJOR.MINOR.PATCH, ej. 0.2.0)."
        )
    return (int(match[1]), int(match[2]), int(match[3]))


def _current_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit(f"No se encontró __version__ en {VERSION_FILE}")
    return match[1]


def _write_version_file(new_version: str) -> None:
    text = VERSION_FILE.read_text(encoding="utf-8")
    updated = re.sub(
        r'__version__\s*=\s*"[^"]+"', f'__version__ = "{new_version}"', text
    )
    VERSION_FILE.write_text(updated, encoding="utf-8")


def _write_package_json(new_version: str) -> None:
    if not PACKAGE_JSON.exists():
        return
    text = PACKAGE_JSON.read_text(encoding="utf-8")
    # Reemplazo dirigido del campo "version" de nivel superior, no un
    # parseo JSON completo: evita reordenar u opinar sobre el resto del
    # archivo (dependencias, scripts) que un `json.dump` reescribiría.
    updated, count = re.subn(
        r'^(\s*"version":\s*)"[^"]*"', rf'\g<1>"{new_version}"', text, count=1, flags=re.MULTILINE
    )
    if count == 0:
        print(f"[aviso] no se encontró \"version\" en {PACKAGE_JSON} — no se tocó.")
        return
    PACKAGE_JSON.write_text(updated, encoding="utf-8")


def _prepend_changelog_entry(new_version: str) -> None:
    header = f"## [{new_version}] - {date.today().isoformat()}\n\n- \n\n"
    if not CHANGELOG.exists():
        CHANGELOG.write_text(
            "# Changelog\n\n"
            "Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).\n"
            "SAVI sigue [SemVer](https://semver.org/lang/es/).\n\n" + header,
            encoding="utf-8",
        )
        return
    text = CHANGELOG.read_text(encoding="utf-8")
    # Se inserta después del preámbulo (antes de la primera entrada
    # `## [` existente, o al final si el changelog está vacío de entradas).
    marker = "\n## ["
    index = text.find(marker)
    if index == -1:
        CHANGELOG.write_text(text.rstrip() + "\n\n" + header, encoding="utf-8")
    else:
        CHANGELOG.write_text(text[: index + 1] + header + text[index + 1 :], encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Uso: {sys.argv[0]} <nueva-version>  (ej. 0.2.0)")
    new_version = sys.argv[1]
    new_tuple = _parse(new_version)

    current = _current_version()
    if new_tuple <= _parse(current):
        raise SystemExit(
            f"{new_version} no es mayor que la versión actual ({current})."
        )

    _write_version_file(new_version)
    _write_package_json(new_version)
    _prepend_changelog_entry(new_version)

    print(f"Versión {current} -> {new_version}")
    print(f"  {VERSION_FILE.relative_to(ROOT)}")
    print(f"  {PACKAGE_JSON.relative_to(ROOT)}")
    print(f"  {CHANGELOG.relative_to(ROOT)} (completá la entrada antes de commitear)")
    print()
    print("Siguiente paso — completar el CHANGELOG y, cuando esté listo el release:")
    print(f'  git commit -am "chore(release): v{new_version}"')
    print(f"  git tag v{new_version}")


if __name__ == "__main__":
    main()
