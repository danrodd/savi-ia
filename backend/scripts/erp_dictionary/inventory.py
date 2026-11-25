"""Inventario del esquema del ERP para el diccionario (fase 5 de cobertura).

Recorre una o más bases del ERP y arma, por tabla (`Esquema.Tabla`):

- columnas (tipo, nulable, comentario), clave primaria y relaciones (salen y llegan);
- en cuántas bases existe y en cuántas tiene datos, con los conteos **sin nombrar
  la base**: lo que se versiona o se manda al modelo no dice de qué cliente es;
- qué funciones del ERP la mencionan (sirven para entender su uso).

Solo lee el catálogo del motor (`information_schema`, `pg_catalog`) y conteos. No
lee filas de datos.

Uso (las cadenas de conexión van por argumento; el script no lee `.env`):

    uv run python -m scripts.erp_dictionary.inventory \\
        --dsn postgresql://usuario:clave@localhost:5432/base1 \\
        --dsn postgresql://usuario:clave@localhost:5432/base2 \\
        --out ../../savi-datos/diccionario-erp/inventory.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg  # pyright: ignore[reportMissingTypeStubs]

_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast", "public")
# Por debajo de esto el conteo exacto es barato; por encima, la estimación del motor.
EXACT_COUNT_BELOW = 50_000


@dataclass
class Column:
    name: str
    type: str
    nullable: bool
    comment: str | None = None
    # En cuántas de las bases recorridas existe la columna.
    present_in: int = 0


@dataclass
class ForeignKey:
    columns: tuple[str, ...]
    references: str
    ref_columns: tuple[str, ...]


@dataclass
class TableInfo:
    key: str
    module: str
    comment: str | None = None
    columns: dict[str, Column] = field(default_factory=dict[str, Column])
    primary_key: tuple[str, ...] = ()
    foreign_keys: list[ForeignKey] = field(default_factory=list[ForeignKey])
    referenced_by: set[str] = field(default_factory=set[str])
    # Filas por base, sin el nombre de la base. 0 = existe pero vacía.
    rows: list[int] = field(default_factory=list[int])
    functions: set[str] = field(default_factory=set[str])


@dataclass(frozen=True)
class Snapshot:
    """Lo que se leyó de una base, ya en tipos simples (para poder probarlo)."""

    columns: Sequence[Mapping[str, Any]]
    comments: Mapping[str, str]
    column_comments: Mapping[tuple[str, str], str]
    primary_keys: Mapping[str, Sequence[str]]
    foreign_keys: Sequence[Mapping[str, Any]]
    rows: Mapping[str, int]
    functions: Mapping[str, str]


def table_key(schema: str, table: str) -> str:
    return f"{schema}.{table}"


def functions_touching(table: str, functions: Mapping[str, str]) -> set[str]:
    """Funciones cuyo código menciona la tabla (`"Esquema"."Tabla"` o `Esquema.Tabla`)."""
    schema, name = table.split(".", 1)
    pattern = re.compile(
        rf'"?{re.escape(schema)}"?\s*\.\s*"?{re.escape(name)}"?(?![A-Za-z0-9_])',
        re.IGNORECASE,
    )
    return {fn for fn, source in functions.items() if pattern.search(source or "")}


def merge(snapshots: Iterable[Snapshot]) -> dict[str, TableInfo]:
    """Une lo de todas las bases: una entrada por tabla, sin nombrar ninguna base."""
    tables: dict[str, TableInfo] = {}
    for snap in snapshots:
        seen_here: set[str] = set()
        for col in snap.columns:
            key = table_key(col["table_schema"], col["table_name"])
            info = tables.setdefault(key, TableInfo(key=key, module=col["table_schema"]))
            seen_here.add(key)
            column = info.columns.setdefault(
                col["column_name"],
                Column(
                    name=col["column_name"],
                    type=col["data_type"],
                    nullable=col["is_nullable"] == "YES",
                ),
            )
            column.present_in += 1
            comment = snap.column_comments.get((key, col["column_name"]))
            if comment and not column.comment:
                column.comment = comment
        for key in seen_here:
            info = tables[key]
            info.rows.append(snap.rows.get(key, 0))
            if snap.comments.get(key) and not info.comment:
                info.comment = snap.comments[key]
            if not info.primary_key and snap.primary_keys.get(key):
                info.primary_key = tuple(snap.primary_keys[key])
            info.functions |= functions_touching(key, snap.functions)
        for fk in snap.foreign_keys:
            key = table_key(fk["schema"], fk["table"])
            target = table_key(fk["ref_schema"], fk["ref_table"])
            if key not in tables:
                continue
            candidate = ForeignKey(tuple(fk["columns"]), target, tuple(fk["ref_columns"]))
            if candidate not in tables[key].foreign_keys:
                tables[key].foreign_keys.append(candidate)
            if target in tables:
                tables[target].referenced_by.add(f"{key}({', '.join(fk['columns'])})")
    return tables


def to_json(tables: Mapping[str, TableInfo], bases: int) -> dict[str, Any]:
    out: dict[str, Any] = {"bases": bases, "tables": {}}
    for key in sorted(tables):
        info = tables[key]
        rows = sorted(info.rows, reverse=True)
        out["tables"][key] = {
            "module": info.module,
            "comment": info.comment,
            "primary_key": list(info.primary_key),
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "comment": c.comment,
                    "present_in": c.present_in,
                }
                for c in info.columns.values()
            ],
            "foreign_keys": [
                {
                    "columns": list(fk.columns),
                    "references": fk.references,
                    "ref_columns": list(fk.ref_columns),
                }
                for fk in info.foreign_keys
            ],
            "referenced_by": sorted(info.referenced_by),
            "usage": {
                "present_in": len(rows),
                "with_data": sum(1 for r in rows if r > 0),
                "max_rows": rows[0] if rows else 0,
            },
            "functions": sorted(info.functions),
        }
    return out


# ── Lectura de una base ─────────────────────────────────────────────────

_COLUMNS = """
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
  AND table_schema NOT LIKE 'pg_temp%'
ORDER BY table_schema, table_name, ordinal_position
"""

_TABLES = """
SELECT n.nspname AS schema, c.relname AS table, c.reltuples::bigint AS estimate,
       obj_description(c.oid, 'pg_class') AS comment
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname <> ALL($1::text[])
  AND n.nspname NOT LIKE 'pg_temp%'
"""

_COLUMN_COMMENTS = """
SELECT n.nspname AS schema, c.relname AS table, a.attname AS column,
       col_description(c.oid, a.attnum) AS comment
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.attnum > 0 AND col_description(c.oid, a.attnum) IS NOT NULL
  AND n.nspname <> ALL($1::text[])
"""

_CONSTRAINTS = """
SELECT n.nspname AS schema, c.relname AS table, con.contype AS kind,
       ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(n, i)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n
             ORDER BY k.i) AS columns,
       rn.nspname AS ref_schema, rc.relname AS ref_table,
       ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(n, i)
             JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n
             ORDER BY k.i) AS ref_columns
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class rc ON rc.oid = con.confrelid
LEFT JOIN pg_namespace rn ON rn.oid = rc.relnamespace
WHERE con.contype IN ('p', 'f') AND n.nspname <> ALL($1::text[])
"""

_FUNCTIONS = """
SELECT n.nspname || '.' || p.proname AS name, p.prosrc AS source
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname <> ALL($1::text[]) AND p.prokind IN ('f', 'p')
"""


async def read_snapshot(dsn: str) -> Snapshot:
    conn: Any = await asyncpg.connect(dsn)  # pyright: ignore[reportUnknownMemberType]
    try:
        await conn.execute("SET default_transaction_read_only = on")
        system = list(_SYSTEM_SCHEMAS)
        columns = [dict(r) for r in await conn.fetch(_COLUMNS)]
        tables = await conn.fetch(_TABLES, system)
        rows: dict[str, int] = {}
        comments: dict[str, str] = {}
        for t in tables:
            key = table_key(t["schema"], t["table"])
            if t["comment"]:
                comments[key] = t["comment"]
            estimate = int(t["estimate"] or 0)
            if estimate < EXACT_COUNT_BELOW:
                quoted = f'"{t["schema"]}"."{t["table"]}"'
                estimate = int(await conn.fetchval(f"SELECT COUNT(*) FROM {quoted}"))
            rows[key] = estimate
        column_comments = {
            (table_key(r["schema"], r["table"]), r["column"]): r["comment"]
            for r in await conn.fetch(_COLUMN_COMMENTS, system)
        }
        primary_keys: dict[str, list[str]] = {}
        foreign_keys: list[dict[str, Any]] = []
        for r in await conn.fetch(_CONSTRAINTS, system):
            key = table_key(r["schema"], r["table"])
            if r["kind"] == "p":
                primary_keys[key] = list(r["columns"])
            elif r["ref_table"]:
                foreign_keys.append(dict(r))
        functions = {r["name"]: r["source"] or "" for r in await conn.fetch(_FUNCTIONS, system)}
    finally:
        await conn.close()
    return Snapshot(
        columns=columns,
        comments=comments,
        column_comments=column_comments,
        primary_keys=primary_keys,
        foreign_keys=foreign_keys,
        rows=rows,
        functions=functions,
    )


async def collect(dsns: Sequence[str]) -> tuple[dict[str, TableInfo], int]:
    snapshots = [await read_snapshot(dsn) for dsn in dsns]
    return merge(snapshots), len(snapshots)


def main(dsns: Sequence[str], out: Path) -> None:
    tables, bases = asyncio.run(collect(dsns))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(to_json(tables, bases), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    with_data = sum(1 for t in tables.values() if any(r > 0 for r in t.rows))
    print(f"{len(tables)} tablas ({with_data} con datos en alguna base) -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", action="append", required=True, help="Una por base.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main(args.dsn, args.out)
