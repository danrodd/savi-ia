"""Diccionario del ERP: qué es cada tabla y columna (fase 5 de cobertura).

Lo consulta el modelo antes de escribir SQL libre, en lugar de explorar
`information_schema` y adivinar por los nombres. Vive en
`data/erp_dictionary/<Modulo>.json` (uno por esquema del ERP), generado por
`scripts/erp_dictionary/build.py` desde el inventario y el borrador.

Cada tabla trae `validado`: `False` es un borrador redactado por IA solo con la
estructura, que el equipo del ERP todavía no revisó. El modelo lo usa como pista.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

DICTIONARY_DIR = Path(__file__).resolve().parents[1] / "data" / "erp_dictionary"
MAX_MATCHES = 8


def fold(text: str) -> str:
    """Minúsculas y sin tildes: "Retención" y "retencion" son lo mismo."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@dataclass(frozen=True)
class ErpTable:
    key: str
    description: str
    validated: bool
    columns: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    primary_key: tuple[str, ...] = ()
    points_to: tuple[str, ...] = ()
    referenced_by: tuple[str, ...] = ()

    def detail(self) -> dict[str, Any]:
        return {
            "tabla": self.key,
            "descripcion": self.description,
            "validado": self.validated,
            "clave_primaria": list(self.primary_key),
            "columnas": [{"nombre": name, **info} for name, info in self.columns.items()],
            "apunta_a": list(self.points_to),
            "la_referencian": list(self.referenced_by),
        }

    def summary(self) -> dict[str, Any]:
        return {"tabla": self.key, "descripcion": self.description, "validado": self.validated}


class ErpDictionary:
    def __init__(self, tables: dict[str, ErpTable]) -> None:
        self._tables = tables
        self._by_folded = {fold(k): t for k, t in tables.items()}
        self._haystack = {
            key: fold(
                " ".join(
                    [
                        key,
                        table.description,
                        *table.columns,
                        *(c.get("descripcion", "") for c in table.columns.values()),
                    ]
                )
            )
            for key, table in tables.items()
        }

    def __len__(self) -> int:
        return len(self._tables)

    def search(self, query: str) -> dict[str, Any]:
        """`Esquema.Tabla` exacto devuelve la ficha; un tema, las tablas candidatas."""
        text = query.strip().strip('"').replace('"."', ".")
        exact = self._by_folded.get(fold(text))
        if exact is not None:
            return {"tabla": exact.detail()}
        words = [w for w in fold(text).replace(".", " ").split() if len(w) >= 3]
        if not words:
            return {"matches": [], "nota": "Indique una tabla (Esquema.Tabla) o un tema."}
        scored: list[tuple[int, str]] = []
        for key, hay in self._haystack.items():
            name = fold(key)
            score = sum(3 if w in name else 1 for w in words if w in hay)
            if score:
                scored.append((score, key))
        scored.sort(key=lambda s: (-s[0], s[1]))
        matches = [self._tables[k].summary() for _, k in scored[:MAX_MATCHES]]
        if not matches:
            return {
                "matches": [],
                "nota": "El diccionario no tiene esa tabla o tema; explore el esquema.",
            }
        return {
            "matches": matches,
            "nota": "Pida el detalle con la tabla exacta (Esquema.Tabla) antes de escribir el SQL.",
        }


def _table(key: str, raw: dict[str, Any]) -> ErpTable:
    columns = cast(dict[str, dict[str, str]], raw.get("columnas") or {})
    return ErpTable(
        key=key,
        description=str(raw.get("descripcion") or ""),
        validated=bool(raw.get("validado")),
        columns=columns,
        primary_key=tuple(raw.get("clave_primaria") or ()),
        points_to=tuple(raw.get("apunta_a") or ()),
        referenced_by=tuple(raw.get("la_referencian") or ()),
    )


def load_dictionary(directory: Path = DICTIONARY_DIR) -> ErpDictionary:
    tables: dict[str, ErpTable] = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        for key, raw in data.items():
            tables[key] = _table(key, cast(dict[str, Any], raw))
    return ErpDictionary(tables)


@lru_cache(maxsize=1)
def get_erp_dictionary() -> ErpDictionary:
    """Se carga una vez por proceso: son archivos del build, no cambian en caliente."""
    return load_dictionary()
