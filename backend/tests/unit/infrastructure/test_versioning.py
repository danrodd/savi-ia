"""Versionado: la versión es el tag de git y nada más.

Tres cosas que se rompen en silencio:

1. El salto que calcula `scripts/version.py` desde los conventional
   commits (un `feat` que sube el parche publica una funcionalidad como
   si fuera un arreglo).
2. El orden de resolución en runtime: la instalación empaquetada tiene
   que usar la versión incrustada por el build, nunca recalcularla.
3. `GET /version` sin autenticación, que es lo que consulta soporte.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

import app._version as version_module
from app.infrastructure.config import get_settings

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "version.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_version_script_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


# ── Cálculo del siguiente número ─────────────────────────────────────


def _commits(*messages: str) -> list[object]:
    return [c for c in (script.parse_commit(m) for m in messages) if c is not None]


@pytest.mark.parametrize(
    ("current", "messages", "expected"),
    [
        ((1, 4, 0), ["fix(chat): corregir el título"], (1, 4, 1)),
        ((1, 4, 0), ["perf(db): índice de conversaciones"], (1, 4, 1)),
        ((1, 4, 2), ["fix: a", "feat(llm): gemini"], (1, 5, 0)),
        ((1, 4, 2), ["feat!: cambia el contrato de /chat"], (2, 0, 0)),
        ((1, 4, 2), ["refactor: x\n\nBREAKING CHANGE: el endpoint cambió"], (2, 0, 0)),
        # Antes de 1.0.0 un cambio que rompe sube el menor: 1.0.0 se decide.
        ((0, 3, 1), ["feat!: nuevo esquema"], (0, 4, 0)),
    ],
)
def test_next_version_follows_conventional_commits(
    current: tuple[int, int, int], messages: list[str], expected: tuple[int, int, int]
) -> None:
    assert script.next_version(current, _commits(*messages)) == expected


def test_commits_that_do_not_change_the_product_do_not_release() -> None:
    commits = _commits("docs: guía", "chore(deps): bump", "test: e2e", "refactor: limpiar")

    assert script.next_version((1, 0, 0), commits) is None


def test_non_conventional_subjects_are_ignored() -> None:
    assert script.parse_commit("Merge branch 'main' into feature") is None
    assert script.parse_commit("arreglos varios") is None


def test_release_notes_group_by_type_and_skip_non_releasable() -> None:
    commits = [c for c in _commits("feat(chat): exportar", "fix: login", "docs: x") if c.releasable]

    notes = script.release_notes("v1.1.0", commits)

    assert notes.startswith("v1.1.0\n")
    assert "## Funcionalidades\n\n- **chat**: exportar" in notes
    assert "## Correcciones\n\n- login" in notes
    assert "docs" not in notes


def test_tag_format_is_enforced() -> None:
    assert script.parse_tag("v2.10.3") == (2, 10, 3)
    with pytest.raises(script.VersionError):
        script.parse_tag("2.10.3")


# ── Ciclo completo contra un repositorio git descartable ─────────────


def _run_git(repo: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _run_git(tmp_path, "init", "-q", "-b", "main")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    return tmp_path


def _commit(repo: Path, message: str) -> None:
    (repo / "archivo.txt").write_text(message, encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", message)


def test_tag_lifecycle_first_explicit_then_calculated(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, "feat: primera funcionalidad")

    # Sin tags: describe devuelve el commit y la versión no se calcula.
    assert script.describe() == script.short_commit()
    with pytest.raises(script.VersionError, match="no se calcula"):
        script.cmd_create(None)

    script.cmd_create("v1.0.0")
    assert script.describe() == "v1.0.0"

    _commit(repo, "docs: solo documentación")
    with pytest.raises(script.VersionError, match="no corresponde"):
        script.cmd_create(None)

    _commit(repo, "feat(chat): exportar conversación")
    assert script.describe().startswith("v1.0.0-2-g")
    script.cmd_create(None)

    assert script.describe() == "v1.1.0"
    notes = _run_git(repo, "tag", "-l", "--format=%(contents)", "v1.1.0")
    assert "- **chat**: exportar conversación" in notes
    # git borra por defecto las líneas con `#` de un mensaje: los títulos
    # de las notas tienen que sobrevivir.
    assert "## Funcionalidades" in notes
    assert "git push origin v1.1.0" in capsys.readouterr().out


def test_create_refuses_dirty_tree_duplicate_tag_and_older_number(repo: Path) -> None:
    _commit(repo, "feat: base")
    script.cmd_create("v1.0.0")

    with pytest.raises(script.VersionError, match="ya tiene un tag"):
        script.cmd_create("v1.0.1")

    _commit(repo, "fix: algo")
    with pytest.raises(script.VersionError, match="no es mayor"):
        script.cmd_create("v0.9.0")

    (repo / "archivo.txt").write_text("sin commitear", encoding="utf-8")
    assert script.describe().endswith("-sucio")
    with pytest.raises(script.VersionError, match="sin commitear"):
        script.cmd_create(None)


def test_create_only_on_main(repo: Path) -> None:
    _commit(repo, "feat: base")
    _run_git(repo, "checkout", "-q", "-b", "develop")

    with pytest.raises(script.VersionError, match="solo en main"):
        script.cmd_create("v1.0.0")


# ── Candidatas (-rc.N) ───────────────────────────────────────────────


def test_next_candidate_tag_numbers_the_candidates_of_a_version() -> None:
    assert script.next_candidate_tag("v1.4.0", []) == "v1.4.0-rc.1"
    assert script.next_candidate_tag("v1.4.0", ["v1.4.0-rc.1", "v1.4.0-rc.2"]) == "v1.4.0-rc.3"
    # Las candidatas de otra versión no cuentan; el 10 va después del 9.
    assert script.next_candidate_tag("v1.4.0", ["v1.3.0-rc.7", "v1.4.0-rc.9"]) == "v1.4.0-rc.10"


def _staging(repo: Path) -> None:
    _commit(repo, "feat: base")
    script.cmd_create("v1.0.0")
    _run_git(repo, "checkout", "-q", "-b", "staging")


def test_candidates_are_created_only_on_staging(repo: Path) -> None:
    _commit(repo, "feat: base")
    script.cmd_create("v1.0.0")
    _commit(repo, "feat(chat): exportar")

    with pytest.raises(script.VersionError, match="solo en staging"):
        script.cmd_create(None, candidate=True)

    _run_git(repo, "checkout", "-q", "-b", "staging")
    script.cmd_create(None, candidate=True)
    assert _run_git(repo, "tag", "--points-at", "HEAD") == "v1.1.0-rc.1"


def test_final_tags_are_still_created_only_on_main(repo: Path) -> None:
    _staging(repo)
    _commit(repo, "feat: algo")

    with pytest.raises(script.VersionError, match="solo en main"):
        script.cmd_create(None)


def test_candidate_lifecycle_rc1_rc2_final_on_the_same_commit(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _staging(repo)
    _commit(repo, "feat(chat): exportar conversación")

    script.cmd_create(None, candidate=True)
    assert script.describe() == "v1.1.0-rc.1"
    assert script.version_number() == "1.1.0"
    # Las candidatas no son "la última versión publicada".
    assert script.last_tag() == "v1.0.0"
    notes = _run_git(repo, "tag", "-l", "--format=%(contents)", "v1.1.0-rc.1")
    assert notes.splitlines()[0] == "v1.1.0-rc.1"
    assert "- **chat**: exportar conversación" in notes
    assert "git push origin v1.1.0-rc.1" in capsys.readouterr().out

    # Sin commits nuevos no se versiona otra vez el mismo commit.
    with pytest.raises(script.VersionError, match="ya tiene un tag"):
        script.cmd_create(None, candidate=True)

    _commit(repo, "fix(chat): corregir el título")
    assert script.describe().startswith("v1.1.0-rc.1-1-g")
    script.cmd_create(None, candidate=True)
    assert script.describe() == "v1.1.0-rc.2"

    # La final se crea en main, sobre el mismo commit que se probó como rc.2.
    _run_git(repo, "checkout", "-q", "main")
    _run_git(repo, "merge", "-q", "--ff-only", "staging")
    script.cmd_create(None)
    assert script.describe() == "v1.1.0"
    assert script.version_number() == "1.1.0"
    assert script.last_tag() == "v1.1.0"
    assert sorted(_run_git(repo, "tag", "--points-at", "HEAD").split()) == [
        "v1.1.0",
        "v1.1.0-rc.2",
    ]


def test_describe_marks_a_dirty_final_tag(repo: Path) -> None:
    _staging(repo)
    _run_git(repo, "checkout", "-q", "main")
    (repo / "archivo.txt").write_text("sin commitear", encoding="utf-8")

    assert script.describe() == "v1.0.0-sucio"


def test_rc_flag_needs_create() -> None:
    with pytest.raises(SystemExit):
        script.main(["--rc"])


# ── Resolución en runtime ────────────────────────────────────────────


def test_packaged_build_version_wins_over_git(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ModuleType("app._build_version")
    fake.VERSION = "v1.4.0"  # type: ignore[attr-defined]
    fake.COMMIT = "bf8eee7"  # type: ignore[attr-defined]
    fake.BUILT_AT = "2026-09-14T15:00:00Z"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app._build_version", fake)

    assert version_module._resolve() == ("v1.4.0", "bf8eee7", "2026-09-14T15:00:00Z")  # pyright: ignore[reportPrivateUsage]


def test_without_build_nor_git_reports_dev_not_a_real_looking_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(version_module, "_from_build", lambda: None)
    monkeypatch.setattr(version_module, "_from_git", lambda: None)

    assert version_module._resolve() == ("0.0.0-dev", None, None)  # pyright: ignore[reportPrivateUsage]


# ── GET /version ─────────────────────────────────────────────────────


def test_version_endpoint_is_public(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DB_ENGINE", "sqlite")
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "savi.db"))
    get_settings.cache_clear()
    import app.main as main_module

    try:
        # Sin context manager: no se dispara el lifespan (no hace falta BD).
        response = TestClient(main_module.create_app()).get("/version")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == version_module.__version__
    assert set(body) == {"version", "commit", "compilado", "entorno"}
