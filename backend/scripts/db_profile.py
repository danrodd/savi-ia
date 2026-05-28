"""Database profiler para farmacias_similares (cliente real del ERP).

Genera un mapa de la BD con DATOS reales (no solo estructura): qué schemas
y tablas tienen filas, cuántas, columnas, FKs y samples de las tablas
pobladas. La salida va a archivos en scripts/db_analysis/ para no inundar
la consola.

Uso:
    uv run python scripts/db_profile.py

Lee la conexión del ERP desde Settings (.env). Pool readonly.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import asyncpg

from app.infrastructure.config import get_settings

OUT_DIR = Path(__file__).parent / "db_analysis"
OUT_DIR.mkdir(exist_ok=True)


def _dsn() -> str:
    s = get_settings()
    return (
        f"postgresql://{s.erp_db_user}:{s.erp_db_password}"
        f"@{s.erp_db_host}:{s.erp_db_port}/{s.erp_db_name}"
    )


async def _fetch(conn: asyncpg.Connection, sql: str, *args: Any) -> list[dict[str, Any]]:
    rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


async def profile() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        # ── 1. Schemas de usuario (excluir catálogos del sistema) ─────────
        schemas = await _fetch(
            conn,
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
              AND schema_name NOT LIKE 'pg_%'
            ORDER BY schema_name
            """,
        )
        schema_names = [s["schema_name"] for s in schemas]
        print(f"Schemas de usuario: {len(schema_names)}")

        # ── 2. Conteo de filas por tabla (vía estadísticas del planner) ───
        # pg_class.reltuples es una estimación rápida (no scan completo).
        table_stats = await _fetch(
            conn,
            """
            SELECT n.nspname AS schema,
                   c.relname AS table,
                   c.reltuples::bigint AS est_rows
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname = ANY($1::text[])
            ORDER BY c.reltuples DESC
            """,
            schema_names,
        )

        populated = [t for t in table_stats if (t["est_rows"] or 0) > 0]
        empty = [t for t in table_stats if (t["est_rows"] or 0) <= 0]
        print(f"Tablas totales: {len(table_stats)}")
        print(f"  Con datos (estimado): {len(populated)}")
        print(f"  Vacías (estimado):    {len(empty)}")

        # Guardar el ranking completo de tablas pobladas.
        (OUT_DIR / "01_table_rowcounts.md").write_text(
            "# Tablas con datos (ordenadas por filas estimadas)\n\n"
            "| Schema | Tabla | Filas (est.) |\n|---|---|---|\n"
            + "\n".join(
                f"| {t['schema']} | {t['table']} | {t['est_rows']:,} |"
                for t in populated
            )
            + f"\n\n**Total tablas con datos: {len(populated)} de {len(table_stats)}**\n",
            encoding="utf-8",
        )

        # ── 3. Resumen por schema: cuántas tablas pobladas y total filas ──
        per_schema: dict[str, dict[str, int]] = {}
        for t in table_stats:
            sc = t["schema"]
            per_schema.setdefault(sc, {"tablas": 0, "pobladas": 0, "filas": 0})
            per_schema[sc]["tablas"] += 1
            if (t["est_rows"] or 0) > 0:
                per_schema[sc]["pobladas"] += 1
                per_schema[sc]["filas"] += int(t["est_rows"])

        schema_ranking = sorted(
            per_schema.items(), key=lambda kv: kv[1]["filas"], reverse=True
        )
        (OUT_DIR / "02_schema_summary.md").write_text(
            "# Resumen por schema (dominios del ERP)\n\n"
            "| Schema | Tablas | Con datos | Filas totales (est.) |\n|---|---|---|---|\n"
            + "\n".join(
                f"| {sc} | {v['tablas']} | {v['pobladas']} | {v['filas']:,} |"
                for sc, v in schema_ranking
            )
            + "\n",
            encoding="utf-8",
        )

        # ── 4. Top 60 tablas pobladas: columnas + FKs + sample 2 filas ────
        top_tables = populated[:60]
        detail_lines: list[str] = ["# Detalle de las 60 tablas con más datos\n"]
        catalog: dict[str, Any] = {}

        for t in top_tables:
            sc, tb, rows = t["schema"], t["table"], t["est_rows"]
            cols = await _fetch(
                conn,
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                ORDER BY ordinal_position
                """,
                sc,
                tb,
            )
            fks = await _fetch(
                conn,
                """
                SELECT kcu.column_name,
                       ccu.table_schema AS ref_schema,
                       ccu.table_name AS ref_table,
                       ccu.column_name AS ref_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = $1 AND tc.table_name = $2
                """,
                sc,
                tb,
            )
            # Sample real de 2 filas (puede tener data sensible — solo para
            # análisis local, NO se commitea db_analysis/).
            try:
                sample = await _fetch(
                    conn, f'SELECT * FROM "{sc}"."{tb}" LIMIT 2'
                )
            except Exception as e:  # noqa: BLE001
                sample = [{"_error": str(e)}]

            catalog[f"{sc}.{tb}"] = {
                "est_rows": int(rows),
                "columns": [
                    {"name": c["column_name"], "type": c["data_type"]}
                    for c in cols
                ],
                "foreign_keys": fks,
            }

            detail_lines.append(f"\n## {sc}.{tb}  ({rows:,} filas est.)\n")
            detail_lines.append("**Columnas:**\n")
            for c in cols:
                null = "" if c["is_nullable"] == "YES" else " NOT NULL"
                detail_lines.append(
                    f"- `{c['column_name']}` {c['data_type']}{null}"
                )
            if fks:
                detail_lines.append("\n**Foreign keys:**\n")
                for fk in fks:
                    detail_lines.append(
                        f"- `{fk['column_name']}` → "
                        f"`{fk['ref_schema']}.{fk['ref_table']}.{fk['ref_column']}`"
                    )
            detail_lines.append("\n**Sample (2 filas):**\n```json")
            detail_lines.append(
                json.dumps(sample, default=str, ensure_ascii=False, indent=2)[:2000]
            )
            detail_lines.append("```\n")

        (OUT_DIR / "03_top_tables_detail.md").write_text(
            "\n".join(detail_lines), encoding="utf-8"
        )
        (OUT_DIR / "catalog.json").write_text(
            json.dumps(catalog, default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\nReportes escritos en {OUT_DIR}/")
        print("  01_table_rowcounts.md  — ranking de tablas pobladas")
        print("  02_schema_summary.md   — dominios por volumen")
        print("  03_top_tables_detail.md — columnas/FKs/samples top 60")
        print("  catalog.json           — catálogo estructurado")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(profile())
