"""Borrador del diccionario del ERP con IA, **solo con la estructura** (fase 5).

Por cada tabla del inventario con datos en alguna base, le pide al modelo una
descripción de la tabla y de sus columnas, y las dudas que el equipo del ERP
tendría que confirmar. Al modelo le llega:

- nombre de la tabla, columnas (nombre, tipo, nulable, comentario), clave primaria;
- relaciones (a qué tablas apunta y cuáles la referencian);
- nombres de las funciones del ERP que la tocan;
- uso aproximado (en cuántas bases tiene datos y el orden de magnitud de filas).

**Nunca** filas, valores ni nombres de bases o clientes (decisión del 2026-11-25).

Usa el proveedor de IA activo del backend (hoy solo OpenAI). Se puede cortar y
volver a correr: lo que ya está en el archivo de salida no se pide de nuevo.

    uv run python -m scripts.erp_dictionary.draft \\
        --inventory ../../savi-datos/diccionario-erp/inventory.json \\
        --out ../../savi-datos/diccionario-erp/draft.json [--dry-run] [--limit 5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

MAX_REFERENCED_BY = 15
MAX_FUNCTIONS = 15
CONCURRENCY = 4

SYSTEM_PROMPT = """Eres analista del ERP de SEO Group (PostgreSQL; esquemas por módulo:
Contabilidad, CuentaCobrar, CuentaPagar, Inventario, Nomina, Tercero, etc.). Te paso la
estructura de UNA tabla, sin datos. Redacta en español neutro, para usuarios funcionales y
para un asistente que escribe SQL:

- "descripcion": qué guarda la tabla y para qué sirve en el negocio (2 a 4 frases).
- "columnas": para cada columna, qué significa en el negocio (una frase corta). Si es una
  clave foránea, di a qué apunta. Si un booleano o un código tiene valores que conviene
  explicar y los puedes deducir, dilo; si no, dilo como duda.
- "dudas": lo que NO puedes deducir de la estructura y el equipo del ERP debe confirmar
  (significado de códigos, estados, signos, cuándo se llena una columna). Máximo 5.

No inventes: si algo es suposición, escribe "posiblemente". Responde SOLO un objeto JSON
con las claves "descripcion", "columnas" (objeto columna -> texto) y "dudas" (lista)."""


def _magnitude(rows: int) -> str:
    if rows <= 0:
        return "vacía"
    if rows < 100:
        return "decenas de filas"
    return f"del orden de 10^{int(math.log10(rows))} filas"


def build_payload(key: str, table: Mapping[str, Any], bases: int) -> dict[str, Any]:
    """Lo único que se manda al modelo por tabla: estructura, nunca datos."""
    usage = table["usage"]
    return {
        "tabla": key,
        "comentario_en_la_base": table.get("comment"),
        "clave_primaria": table.get("primary_key", []),
        "columnas": [
            {
                "nombre": c["name"],
                "tipo": c["type"],
                "nulable": c["nullable"],
                **({"comentario": c["comment"]} if c.get("comment") else {}),
            }
            for c in table["columns"]
        ],
        "apunta_a": [
            f"{', '.join(fk['columns'])} -> {fk['references']}({', '.join(fk['ref_columns'])})"
            for fk in table.get("foreign_keys", [])
        ],
        "la_referencian": table.get("referenced_by", [])[:MAX_REFERENCED_BY],
        "funciones_que_la_usan": table.get("functions", [])[:MAX_FUNCTIONS],
        "uso": (
            f"con datos en {usage['with_data']} de {bases} bases; "
            f"{_magnitude(int(usage['max_rows']))}"
        ),
    }


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_draft(text: str, columns: list[str]) -> dict[str, Any]:
    """El JSON del modelo, normalizado. Las columnas que no describió quedan vacías."""
    data = json.loads(_FENCE.sub("", text.strip()))
    if not isinstance(data, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    raw = cast(dict[str, Any], data)
    described = raw.get("columnas") or {}
    if not isinstance(described, dict):
        described = {}
    described = cast(dict[str, Any], described)
    dudas = raw.get("dudas") or []
    return {
        "descripcion": str(raw.get("descripcion") or "").strip(),
        "columnas": {c: str(described.get(c) or "").strip() for c in columns},
        "dudas": [str(d).strip() for d in cast(list[Any], dudas) if str(d).strip()][:5]
        if isinstance(dudas, list)
        else [],
    }


async def _draft_one(
    client: Any, model: str, payload: dict[str, Any], columns: list[str]
) -> tuple[dict[str, Any], int, int]:
    response = await client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=json.dumps(payload, ensure_ascii=False),
        store=False,
    )
    usage = getattr(response, "usage", None)
    tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
    return parse_draft(str(response.output_text), columns), tokens_in, tokens_out


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


async def run(inventory: Path, out: Path, *, dry_run: bool, limit: int | None) -> None:
    data = _load(inventory)
    bases = int(data["bases"])
    pending = {
        key: table for key, table in data["tables"].items() if table["usage"]["with_data"] > 0
    }
    done: dict[str, Any] = _load(out)
    todo = [k for k in sorted(pending) if k not in done][: limit or None]
    print(f"{len(pending)} tablas con datos; {len(done)} ya hechas; {len(todo)} por hacer.")
    if dry_run:
        for key in todo[:3]:
            print(json.dumps(build_payload(key, pending[key], bases), ensure_ascii=False, indent=1))
        return

    from openai import AsyncOpenAI

    from app.infrastructure.config import get_settings
    from app.infrastructure.database.pool import init_engines
    from app.modules.llm_providers.infrastructure.active_provider_resolver import (
        init_active_provider_resolver,
    )
    from app.modules.llm_providers.infrastructure.http.dependencies import (
        build_llm_provider_repository,
    )

    settings = get_settings()
    init_engines(settings)
    provider = await init_active_provider_resolver(
        build_llm_provider_repository(settings)
    ).resolve()
    if provider.kind != "openai" or not provider.credential:
        raise SystemExit(f"Solo OpenAI con clave por ahora (proveedor activo: {provider.kind}).")
    client = AsyncOpenAI(api_key=provider.credential)
    price = provider.pricing.get(provider.chat_model)
    gate = asyncio.Semaphore(CONCURRENCY)
    totals = {"in": 0, "out": 0, "fallidas": 0}

    async def one(key: str) -> None:
        columns = [c["name"] for c in pending[key]["columns"]]
        async with gate:
            try:
                draft, tin, tout = await _draft_one(
                    client, provider.chat_model, build_payload(key, pending[key], bases), columns
                )
            except Exception as e:  # noqa: BLE001 — una tabla fallida no corta el lote
                totals["fallidas"] += 1
                print(f"  falló {key}: {type(e).__name__}")
                return
        totals["in"] += tin
        totals["out"] += tout
        done[key] = {**draft, "validado": False, "modelo": provider.chat_model}
        _save(out, done)
        print(f"  {key}")

    await asyncio.gather(*(one(k) for k in todo))
    cost = (
        (totals["in"] * price.input + totals["out"] * price.output) / 1_000_000 if price else None
    )
    print(
        f"Listo: {len(done)} tablas. Tokens {totals['in']} entrada / {totals['out']} salida; "
        f"costo {f'US$ {cost:.2f}' if cost is not None else 'sin precio configurado'}; "
        f"fallidas {totals['fallidas']}."
    )


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Muestra lo que se enviaría.")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de tablas a pedir.")
    args = parser.parse_args()
    asyncio.run(run(args.inventory, args.out, dry_run=args.dry_run, limit=args.limit))
