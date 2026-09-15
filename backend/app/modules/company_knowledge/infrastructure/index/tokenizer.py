"""Tokenización para el ranking léxico (BM25).

Normaliza como la escribe un usuario apurado: minúsculas y sin tildes
(`facturación` → `facturacion`). Conserva códigos compuestos además de sus
partes (`FE-1234` → `fe`, `1234`, `fe1234`), porque "el acta POL-DSC-19"
es exactamente la pregunta que la búsqueda vectorial resuelve peor.
"""

import re
import unicodedata

_TOKEN = re.compile(r"[a-z0-9]+(?:[-_./][a-z0-9]+)*")
_SEPARATORS = re.compile(r"[-_./]")

# Palabras vacías frecuentes del español. Sin stemming en v1 (spec §2.3).
_STOPWORDS = frozenset(
    [
        "a",
        "al",
        "algo",
        "algun",
        "alguna",
        "algunas",
        "alguno",
        "algunos",
        "ante",
        "antes",
        "aqui",
        "asi",
        "aun",
        "cada",
        "como",
        "con",
        "contra",
        "cual",
        "cuales",
        "cuando",
        "de",
        "del",
        "desde",
        "donde",
        "dos",
        "el",
        "ella",
        "ellas",
        "ello",
        "ellos",
        "en",
        "entre",
        "era",
        "eran",
        "es",
        "esa",
        "esas",
        "ese",
        "eso",
        "esos",
        "esta",
        "estaba",
        "estado",
        "estan",
        "estar",
        "este",
        "esto",
        "estos",
        "fue",
        "fueron",
        "ha",
        "habia",
        "han",
        "hasta",
        "hay",
        "la",
        "las",
        "le",
        "les",
        "lo",
        "los",
        "mas",
        "me",
        "mi",
        "mis",
        "mucho",
        "muy",
        "nada",
        "ni",
        "no",
        "nos",
        "nosotros",
        "o",
        "os",
        "otra",
        "otras",
        "otro",
        "otros",
        "para",
        "pero",
        "poco",
        "por",
        "porque",
        "que",
        "quien",
        "quienes",
        "se",
        "sea",
        "segun",
        "ser",
        "si",
        "sin",
        "sobre",
        "solo",
        "son",
        "su",
        "sus",
        "tambien",
        "tan",
        "tanto",
        "te",
        "tiene",
        "tienen",
        "todo",
        "todos",
        "tu",
        "tus",
        "un",
        "una",
        "unas",
        "uno",
        "unos",
        "usted",
        "ustedes",
        "y",
        "ya",
        "yo",
        "cual",
        "cuanto",
        "cuanta",
        "cuantos",
        "cuantas",
        "debe",
        "deben",
        "puede",
        "pueden",
        "hace",
        "hacer",
    ]
)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    normalized = _strip_accents(text.lower())
    tokens: list[str] = []
    for match in _TOKEN.finditer(normalized):
        raw = match.group(0)
        parts = [part for part in _SEPARATORS.split(raw) if part]
        for part in parts:
            if _keep(part):
                tokens.append(part)
        if len(parts) > 1:
            tokens.append("".join(parts))
    return tokens


def _keep(token: str) -> bool:
    if token in _STOPWORDS:
        return False
    return len(token) > 1 or token.isdigit()
