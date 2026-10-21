"""Guarda del registro: el texto que ve el usuario va de "usted", sin voseo.

SAVI habla en español colombiano formal. Este test recorre las fuentes que
llegan al usuario o al modelo y falla si encuentra formas de voseo
rioplatense ("podés", "revisá", "volvé", "vos"...). Revisa:

- `backend/app/**/*.py`: solo literales de texto (ast), sin comentarios ni
  docstrings, porque lo interno no llega al usuario.
- `frontend/src`: plantillas y literales de `.vue` y `.ts`, sin comentarios
  ni archivos de prueba.
- `installer/` (`.iss`, `.ps1`, `.html`) y `docs/manuales/` (`.html`, `.md`).

Lista de formas: ver `_VOSEO_WORDS` y `_voseo_imperatives`. Es una lista
curada con límites de palabra para no marcar "más", "está", "además", etc.
Si aparece una forma nueva, se agrega a la lista.

Cómo permitir una excepción legítima (por ejemplo, un prompt que NOMBRA el
voseo para prohibirlo): agregar la ruta relativa a la raíz del repo y la
forma exacta (en minúsculas) a `ALLOWED`. No hay marcadores en línea: esas
cadenas viajan al usuario o al modelo y no deben llevar etiquetas.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# ruta relativa (con "/") -> formas permitidas en esa ruta (minúsculas).
ALLOWED: dict[str, set[str]] = {
    # El prompt de sistema nombra el voseo para prohibírselo al modelo.
    "backend/app/modules/chat/infrastructure/llm/system_prompt.py": {
        "podés",
        "tenés",
        "revisá",
    },
}

# Formas indicativas y pronombres que no se derivan de una raíz.
_VOSEO_WORDS = {
    "vos",
    "podés",
    "tenés",
    "querés",
    "sabés",
    "hacés",
    "decís",
    "ponés",
    "venís",
    "andás",
    "contás",
    "necesitás",
    "preferís",
    "pensás",
    "creés",
    "sentís",
    "vivís",
    "salís",
    "tomás",
    "estás",
    "usás",
    "buscás",
    "llamás",
    "mirás",
    "ayudás",
    "esperás",
    "escribís",
    "elegís",
    "abrís",
    "cerrás",
    "pedís",
    "recibís",
    "sumá",
    "acordate",
    "asegurate",
    "fijate",
    "avisame",
    "decime",
    "contame",
    "mostrame",
    "ayudame",
    "pasame",
    "dame",
    "dejame",
    "mandame",
    "listame",
    "comparame",
    "extraeme",
    "ponele",
    "armás",
    "omitís",
    "respetás",
    "aceptás",
    "devolvés",
    "obtenés",
    "filtrás",
    "registrás",
    "atendés",
    "entendés",
    "definís",
    "dejás",
    "hablás",
    "importás",
    "resolvés",
    "subís",
    "tocás",
    "trabajás",
    "cambiás",
    "conectás",
    "pagás",
    "consumís",
    "preguntás",
    "pegás",
}

# Raíces de verbos cuyo imperativo voseante se genera: -ar -> -á, -er -> -é,
# -ir -> -í; y la forma con enclítico sin tilde ("guardalo", "volvete").
_AR = [
    "revis",
    "prob",
    "us",
    "ingres",
    "seleccion",
    "agreg",
    "carg",
    "guard",
    "confirm",
    "intent",
    "contact",
    "copi",
    "peg",
    "complet",
    "configur",
    "gener",
    "activ",
    "desactiv",
    "consult",
    "busc",
    "instal",
    "reinici",
    "inici",
    "actualiz",
    "verific",
    "descarg",
    "edit",
    "cambi",
    "dej",
    "mir",
    "toc",
    "ayud",
    "mand",
    "envi",
    "pas",
    "fij",
    "aclar",
    "cre",
    "cancel",
    "repet",
    "record",
    "indic",
    "especific",
    "borr",
    "elimin",
    "tom",
    "ejecut",
    "reintent",
    "reformul",
    "afin",
    "list",
    "mostr",
    "avis",
    "acept",
    "agrup",
    "aplan",
    "calific",
    "cit",
    "expres",
    "filtr",
    "llam",
    "marc",
    "presion",
    "registr",
    "reinstal",
    "pul",
    "pregunt",
    "explic",
    "arrastr",
    "solt",
    "compart",
    "proyect",
    "limit",
    "mir",
    "desmarc",
    "desvincul",
    "cancel",
    "apret",
    "achic",
    "descart",
    "commite",
]
_ER = [
    "volv",
    "hac",
    "pon",
    "ten",
    "pod",
    "quer",
    "sab",
    "le",
    "corr",
    "ofrec",
    "respond",
    "entend",
    "promet",
    "devolv",
    "obten",
    "resolv",
]
_IR = ["eleg", "abr", "cerr", "escrib", "ped", "sub", "ven", "recib", "dec", "repet", "suger"]
# Sin "se" ni "les": chocan con "usase", "generales" y otras palabras reales.
_CLITICS = ("lo", "la", "los", "las", "le", "me", "nos")


def _voseo_imperatives() -> set[str]:
    out: set[str] = set()
    for root in _AR:
        out.add(f"{root}á")
        out.update(f"{root}a{c}" for c in _CLITICS)
    for root in _ER:
        out.add(f"{root}é")
    for root in _IR:
        out.add(f"{root}í")
        out.update(f"{root}i{c}" for c in _CLITICS)
    out.update({"cliqueá", "andá", "vení", "decí"})
    return out


def _build_pattern() -> re.Pattern[str]:
    forms = sorted(_VOSEO_WORDS | _voseo_imperatives(), key=len, reverse=True)
    body = "|".join(re.escape(f) for f in forms)
    return re.compile(rf"(?<!\w)({body})(?!\w)", re.IGNORECASE)


_PATTERN = _build_pattern()


def _hits(text: str) -> Iterator[tuple[int, str]]:
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _PATTERN.finditer(line):
            yield number, match.group(1).lower()


# --------------------------------------------------------------------- Python


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


def _python_strings(path: Path) -> Iterator[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node.lineno, node.value


# ------------------------------------------------------------ Texto con marcas


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/|<!--.*?-->", re.DOTALL)
_LINE_COMMENT = re.compile(r"(^|\s)//.*$")


def _blank_block_comments(text: str) -> str:
    """Reemplaza los comentarios de bloque por saltos de línea (conserva la numeración)."""
    return _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _strip_frontend_comments(text: str) -> str:
    text = _blank_block_comments(text)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())


def _strip_script_comments(text: str, marker: str) -> str:
    return "\n".join("" if line.lstrip().startswith(marker) else line for line in text.splitlines())


# ------------------------------------------------------------------ Colección


def _frontend_files() -> list[Path]:
    base = ROOT / "frontend" / "src"
    files = [
        p
        for ext in ("*.vue", "*.ts")
        for p in base.rglob(ext)
        if "__tests__" not in p.parts and not re.search(r"\.(spec|test)\.ts$", p.name)
    ]
    return sorted(files)


def _text_files(folder: str, exts: tuple[str, ...]) -> list[Path]:
    base = ROOT / folder
    skip = {"build", "output", "node_modules", "imagenes"}
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file() and p.suffix in exts and not (set(p.relative_to(base).parts) & skip)
    )


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _collect() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []

    def add(path: Path, number: int, word: str) -> None:
        rel = _rel(path)
        if word not in ALLOWED.get(rel, set()):
            found.append((rel, number, word))

    for path in sorted((ROOT / "backend" / "app").rglob("*.py")):
        for line_no, value in _python_strings(path):
            for offset, word in _hits(value):
                add(path, line_no + offset - 1, word)

    for path in _frontend_files():
        text = _strip_frontend_comments(path.read_text(encoding="utf-8"))
        for number, word in _hits(text):
            add(path, number, word)

    for path in _text_files("installer", (".iss", ".ps1", ".html")):
        raw = path.read_text(encoding="utf-8-sig")
        text = _strip_script_comments(raw, ";" if path.suffix == ".iss" else "#")
        if path.suffix == ".html":
            text = _blank_block_comments(raw)
        for number, word in _hits(text):
            add(path, number, word)

    for path in _text_files("docs/manuales", (".html", ".md")):
        for number, word in _hits(_blank_block_comments(path.read_text(encoding="utf-8"))):
            add(path, number, word)

    return found


def test_no_voseo_in_user_facing_text() -> None:
    found = _collect()
    report = "\n".join(f"  {rel}:{line}  {word}" for rel, line, word in found)
    assert not found, (
        "El texto de cara al usuario debe ir de 'usted' (sin voseo). Corrija estas "
        "formas o, si son legítimas, agréguelas a ALLOWED:\n" + report
    )


@pytest.mark.parametrize(
    "text",
    ["Podés revisar", "Revisá el puerto", "Volvé a intentar", "guardalo ahora", "vos mismo"],
)
def test_pattern_detects_voseo(text: str) -> None:
    assert list(_hits(text))


@pytest.mark.parametrize(
    "text",
    [
        "Puede revisar más datos después",
        "Revise el puerto; está disponible",
        "además de inglés y país",
        "Vuelva a intentarlo",
        "usted está en la sesión",
        "Verá los pasos aquí",
    ],
)
def test_pattern_ignores_usted_and_common_words(text: str) -> None:
    assert not list(_hits(text))
