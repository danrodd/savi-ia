"""Versión de SAVI: la calcula a partir del tag de git. Es la única fuente.

No existe un número de versión escrito en ningún otro lado. Todo lo
demás —backend, frontend, instalador— lo deriva de este script en el
momento de compilar. Un número escrito en dos lugares termina
desincronizado, y entonces la aplicación afirma ser una versión que no
es y el problema se busca en el commit equivocado.

Uso (desde la raíz del monorepo, sin dependencias fuera de la stdlib):

    python scripts/version.py              # versión actual (git describe)
    python scripts/version.py --numero     # X.Y.Z del último tag (Inno Setup)
    python scripts/version.py --json       # versión, commit, número y si está sucio
    python scripts/version.py --proponer   # calcula la siguiente y muestra las notas
    python scripts/version.py --crear      # crea el tag anotado calculado
    python scripts/version.py --crear v1.2.0   # o el que decida una persona
    python scripts/version.py --crear --rc     # candidata v1.2.0-rc.N (solo en staging)

Las versiones finales se taguean solo en `main`. Las candidatas (`-rc.N`) se
taguean solo en `staging` y sirven para probar en el canal `beta`: nunca llegan
a `stable`. Orden: v1.4.0-rc.1 < v1.4.0-rc.2 < v1.4.0 < v1.4.1-rc.1.

Qué imprime la versión actual:

    v1.4.0              exactamente en esa versión publicada
    v1.4.0-rc.2         exactamente en esa candidata
    v1.4.0-14-gbf8eee7  14 commits después de v1.4.0, en el commit bf8eee7
    cf07443             todavía no hay ningún tag
    ...-sucio           se construyó con cambios sin commitear

Nunca inventa un número: sin tags devuelve el commit, y si el árbol
tiene cambios, lo dice.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEV_VERSION = "0.0.0-dev"
DIRTY_SUFFIX = "-sucio"
TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# Candidata: `v1.4.0-rc.2`. Va a `beta`, nunca a `stable`.
RC_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-rc\.([1-9]\d*)$")
_COMMIT_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<subject>.+)$"
)

# Tipos que justifican una versión nueva. El resto (docs, chore, ci,
# test, style, refactor) no cambia lo que recibe el usuario.
_RELEASE_TYPES = {"feat", "fix", "perf"}

_GROUP_TITLES = (
    ("breaking", "Cambios que rompen compatibilidad"),
    ("feat", "Funcionalidades"),
    ("fix", "Correcciones"),
    ("perf", "Rendimiento"),
)


class VersionError(Exception):
    """Algo impide calcular o crear la versión. El mensaje es para una persona."""


@dataclass(frozen=True)
class Commit:
    type: str
    scope: str | None
    subject: str
    breaking: bool

    @property
    def releasable(self) -> bool:
        return self.breaking or self.type in _RELEASE_TYPES

    def line(self) -> str:
        scope = f"**{self.scope}**: " if self.scope else ""
        return f"- {scope}{self.subject}"


# ── git ──────────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except FileNotFoundError as e:
        raise VersionError("git no está instalado o no está en el PATH.") from e
    except subprocess.CalledProcessError as e:
        raise VersionError(e.stderr.strip() or f"git {' '.join(args)} falló.") from e
    return result.stdout.strip()


def describe() -> str:
    # Si el commit tiene la final y también una candidata (la final se crea
    # sobre el mismo commit que se probó), manda la final.
    finals = [t for t in _git("tag", "--points-at", "HEAD").split() if TAG_PATTERN.match(t)]
    if finals:
        return max(finals, key=parse_tag) + (DIRTY_SUFFIX if is_dirty() else "")
    return _git("describe", "--tags", "--always", f"--dirty={DIRTY_SUFFIX}", "--match", "v*")


def last_tag() -> str | None:
    """La última versión **final**: las candidatas no cuentan como versión publicada."""
    try:
        return _git("describe", "--tags", "--abbrev=0", "--match", "v*", "--exclude", "*-rc.*")
    except VersionError:
        return None


def version_number() -> str:
    """`X.Y.Z` de la versión que se está construyendo (lo pide Inno Setup).

    Cuenta también las candidatas: un build de `v1.4.0-rc.1` es `1.4.0`, no la
    última final.
    """
    try:
        tag = _git("describe", "--tags", "--abbrev=0", "--match", "v*")
    except VersionError:
        return "0.0.0"
    match = TAG_PATTERN.match(tag) or RC_TAG_PATTERN.match(tag)
    if match is None:
        raise VersionError(f"'{tag}' no tiene el formato vMAYOR.MENOR.PARCHE[-rc.N].")
    return "{}.{}.{}".format(*match.groups()[:3])


def is_dirty() -> bool:
    return bool(_git("status", "--porcelain", "--untracked-files=no"))


def short_commit() -> str:
    return _git("rev-parse", "--short", "HEAD")


def commits_since(tag: str | None) -> list[str]:
    """Mensajes completos (asunto + cuerpo) desde `tag`, del más viejo al más nuevo."""
    rev_range = f"{tag}..HEAD" if tag else "HEAD"
    raw = _git("log", rev_range, "--reverse", "--format=%s%n%b%x1e")
    return [entry.strip() for entry in raw.split("\x1e") if entry.strip()]


# ── cálculo ──────────────────────────────────────────────────────────


def parse_tag(tag: str) -> tuple[int, int, int]:
    match = TAG_PATTERN.match(tag)
    if not match:
        raise VersionError(f"'{tag}' no tiene el formato vMAYOR.MENOR.PARCHE (ej. v1.2.0).")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def parse_commit(message: str) -> Commit | None:
    """`None` si el asunto no sigue conventional commits: no cuenta para el salto."""
    subject, _, body = message.partition("\n")
    match = _COMMIT_PATTERN.match(subject.strip())
    if not match:
        return None
    breaking = bool(match["bang"]) or "BREAKING CHANGE" in body
    return Commit(
        type=match["type"],
        scope=match["scope"] or None,
        subject=match["subject"].strip(),
        breaking=breaking,
    )


def next_version(
    current: tuple[int, int, int], commits: list[Commit]
) -> tuple[int, int, int] | None:
    """El salto que corresponde, o `None` si nada justifica una versión nueva.

    Antes de 1.0.0 SemVer permite romper compatibilidad en cualquier
    versión: un cambio que rompe sube el menor, no el mayor. Pasar a
    1.0.0 es una decisión de negocio y se hace con `--crear v1.0.0`.
    """
    major, minor, patch = current
    if any(c.breaking for c in commits):
        return (major + 1, 0, 0) if major >= 1 else (major, minor + 1, 0)
    if any(c.type == "feat" for c in commits):
        return (major, minor + 1, 0)
    if any(c.type in {"fix", "perf"} for c in commits):
        return (major, minor, patch + 1)
    return None


def release_notes(version: str, commits: list[Commit]) -> str:
    lines = [version, ""]
    for key, title in _GROUP_TITLES:
        if key == "breaking":
            group = [c for c in commits if c.breaking]
        else:
            group = [c for c in commits if c.type == key and not c.breaking]
        if group:
            lines += [f"## {title}", "", *(c.line() for c in group), ""]
    return "\n".join(lines).rstrip() + "\n"


def format_tag(version: tuple[int, int, int]) -> str:
    return "v{}.{}.{}".format(*version)


# ── comandos ─────────────────────────────────────────────────────────


def _proposal() -> tuple[str, str]:
    tag = last_tag()
    if tag is None:
        raise VersionError(
            "Todavía no hay ningún tag: la primera versión no se calcula, se decide. "
            "Creala con: python scripts/version.py --crear vX.Y.Z"
        )
    parsed = [c for c in (parse_commit(m) for m in commits_since(tag)) if c is not None]
    new = next_version(parse_tag(tag), parsed)
    if new is None:
        raise VersionError(
            f"Desde {tag} solo hay commits que no cambian lo que recibe el usuario "
            "(docs, chore, test, refactor…): no corresponde una versión nueva."
        )
    version = format_tag(new)
    releasable = [c for c in parsed if c.releasable]
    return version, release_notes(version, releasable)


def next_candidate_tag(base: str, existing_tags: list[str]) -> str:
    """`v1.4.0` y las candidatas que ya hay → la siguiente (`v1.4.0-rc.3`)."""
    numbers = [
        int(match[4])
        for tag in existing_tags
        if (match := RC_TAG_PATTERN.match(tag)) and tag.startswith(f"{base}-rc.")
    ]
    return f"{base}-rc.{max(numbers, default=0) + 1}"


def cmd_create(explicit: str | None, *, candidate: bool = False) -> None:
    if is_dirty():
        raise VersionError("Hay cambios sin commitear: el tag apuntaría a un árbol que no existe.")
    here = _git("tag", "--points-at", "HEAD").split()
    # La final se crea sobre el mismo commit que se probó como candidata.
    blocking = here if candidate else [t for t in here if not RC_TAG_PATTERN.match(t)]
    if blocking:
        raise VersionError("HEAD ya tiene un tag: no se versiona dos veces el mismo commit.")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    allowed = "staging" if candidate else "main"
    if branch != allowed:
        what = "Las candidatas se crean" if candidate else "Los tags se crean"
        raise VersionError(f"{what} solo en {allowed} (estás en '{branch}').")

    previous = last_tag()
    if explicit:
        new = parse_tag(explicit)
        if previous and new <= parse_tag(previous):
            raise VersionError(f"{explicit} no es mayor que la última versión ({previous}).")
        parsed = [c for c in (parse_commit(m) for m in commits_since(previous)) if c is not None]
        version = explicit
        notes = release_notes(version, [c for c in parsed if c.releasable])
    else:
        version, notes = _proposal()

    if candidate:
        # Mismas notas que la final, con el nombre de la candidata en el título.
        tag = next_candidate_tag(version, _git("tag", "--list", f"{version}-rc.*").split())
        notes = tag + notes[len(version) :]
        version = tag

    # `--cleanup=verbatim`: por defecto git borra del mensaje las líneas que
    # empiezan con `#` (las toma como comentarios) y las notas perderían
    # los títulos "## Funcionalidades", "## Correcciones"…
    _git("tag", "-a", version, "--cleanup=verbatim", "-m", notes)
    print(notes)
    print(f"Tag {version} creado en {short_commit()}. Para publicarlo:")
    print(f"  git push origin {version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--numero", action="store_true", help="X.Y.Z del último tag (0.0.0 sin tags)"
    )
    group.add_argument("--json", action="store_true", help="versión, commit, número y estado")
    group.add_argument("--proponer", action="store_true", help="calcula la siguiente versión")
    group.add_argument("--crear", nargs="?", const="", metavar="vX.Y.Z", help="crea el tag anotado")
    parser.add_argument(
        "--rc", action="store_true", help="con --crear: una candidata (-rc.N), solo en staging"
    )
    args = parser.parse_args(argv)
    if args.rc and args.crear is None:
        parser.error("--rc va junto con --crear.")

    # Windows abre la consola en cp1252: las notas y los errores llevan acentos.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    try:
        if args.numero:
            print(version_number())
        elif args.json:
            print(
                json.dumps(
                    {
                        "version": describe(),
                        "commit": short_commit(),
                        "numero": version_number(),
                        "sucio": is_dirty(),
                    }
                )
            )
        elif args.proponer:
            version, notes = _proposal()
            print(notes)
            print(f"Siguiente versión propuesta: {version}")
        elif args.crear is not None:
            cmd_create(args.crear or None, candidate=args.rc)
        else:
            print(describe())
    except VersionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
