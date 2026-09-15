# ruff: noqa: E501 — script de análisis con tablas anchas.
"""Qué SQL ejecuta de verdad la tool `consultar_libre`.

Paso 0 de la Fase 1 de seguridad: **medir antes de bloquear**. Restringir el
SQL a ciegas rompe respuestas que hoy funcionan; esto lee la tabla de
auditoría (`audit_query`, que ya guarda cada intento) y reporta:

- esquemas y tablas usados, por frecuencia;
- funciones invocadas, marcando las que la Fase 1 bloquearía;
- cuántas consultas históricas quedarían fuera con cada opción de permisos.

Uso:

    uv run python -m scripts.audit_free_query
    uv run python -m scripts.audit_free_query --limite 5000
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter

import sqlglot
from sqlalchemy import text
from sqlglot import exp

from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.pool import init_engines
from app.infrastructure.database.session import get_agent_sessionmaker
from app.modules.free_query.application.sql_validator import (
    BLOCKED_FUNCTION_NAMES,
    BLOCKED_FUNCTION_PREFIXES,
    BLOCKED_SCHEMAS,
)


def _tabla(titulo: str, conteo: Counter[str], total: int) -> None:
    print(f"\n{titulo}")
    if not conteo:
        print("  (ninguno)")
        return
    for nombre, veces in conteo.most_common(30):
        print(f"  {veces:5}  {veces * 100 / max(total, 1):5.1f}%  {nombre}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=2000)
    args = parser.parse_args()

    init_engines(get_settings())
    async with get_agent_sessionmaker()() as session:
        filas = (
            await session.execute(
                text("SELECT sql, result FROM audit_query ORDER BY created_at DESC LIMIT :n"),
                {"n": args.limite},
            )
        ).all()

    if not filas:
        print(
            "La tabla de auditoría está vacía: todavía no se ejecutó ninguna consulta libre.\n"
            "Sin datos históricos, la decisión de permisos se toma por diseño y se revisa\n"
            "cuando haya uso real."
        )
        return

    tablas: Counter[str] = Counter()
    esquemas: Counter[str] = Counter()
    funciones: Counter[str] = Counter()
    resultados: Counter[str] = Counter()
    no_parseables = 0

    for sql, resultado in filas:
        resultados[str(resultado)] += 1
        try:
            arbol = sqlglot.parse_one(str(sql), dialect="postgres")
        except Exception:  # noqa: BLE001 — SQL rechazado que ni parsea
            no_parseables += 1
            continue
        if arbol is None:
            no_parseables += 1
            continue
        for nodo in arbol.find_all(exp.Table):
            esquema = (nodo.db or "").lower()
            esquemas[esquema or "(sin esquema)"] += 1
            tablas[f"{esquema}.{nodo.name}".lstrip(".").lower()] += 1
        for nodo in arbol.find_all(exp.Anonymous, exp.Func):
            nombre = (getattr(nodo, "name", "") or type(nodo).__name__).lower()
            if nombre:
                funciones[nombre] += 1

    total = len(filas)
    print(f"Consultas analizadas: {total} (no parseables: {no_parseables})")
    _tabla("Resultado del intento", resultados, total)
    _tabla("Esquemas", esquemas, total)
    _tabla("Tablas", tablas, total)
    _tabla("Funciones", funciones, total)

    bloqueadas = {
        nombre: veces
        for nombre, veces in funciones.items()
        if nombre in BLOCKED_FUNCTION_NAMES or nombre.startswith(tuple(BLOCKED_FUNCTION_PREFIXES))
    }
    esquemas_bloqueados = {
        nombre: veces for nombre, veces in esquemas.items() if nombre in BLOCKED_SCHEMAS
    }
    print("\n── Impacto de la Fase 1 ──")
    print(f"  Funciones que quedarían bloqueadas: {bloqueadas or 'ninguna'}")
    print(f"  Esquemas de sistema usados: {esquemas_bloqueados or 'ninguno'}")


if __name__ == "__main__":
    asyncio.run(main())
