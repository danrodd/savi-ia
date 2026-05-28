"""Smoke test del query semántico contra farmacias_similares (sin LLM).

Prueba el flujo compilar→ejecutar→formatear con consultas reales.
Uso: uv run python scripts/test_semantic.py
"""
import asyncio

from app.infrastructure.config import get_settings
from app.infrastructure.database import init_engines
from app.modules.data_query.application.run_semantic_query import run_semantic_query


async def main() -> None:
    init_engines(get_settings())

    casos: list[tuple[str, dict]] = [
        (
            "Total facturado y nº de facturas (todo el periodo)",
            {"entidad": "ventas", "modo": "agregado",
             "metricas": ["monto_total", "num_facturas", "ticket_promedio"]},
        ),
        (
            "Ventas por mes (top por monto)",
            {"entidad": "ventas", "modo": "agregado",
             "metricas": ["monto_total"], "dimensiones": ["mes"],
             "orden": {"campo": "mes", "dir": "asc"}, "limite": 12},
        ),
        (
            "Top 10 clientes por monto facturado",
            {"entidad": "ventas", "modo": "agregado",
             "metricas": ["monto_total", "num_facturas"], "dimensiones": ["cliente"],
             "orden": {"campo": "monto_total", "dir": "desc"}, "limite": 10},
        ),
        (
            "Top 10 productos por unidades vendidas",
            {"entidad": "ventas_detalle", "modo": "agregado",
             "metricas": ["unidades", "monto_lineas"], "dimensiones": ["producto"],
             "orden": {"campo": "unidades", "dir": "desc"}, "limite": 10},
        ),
        (
            "Buscar cliente por nombre (detalle, máx 30)",
            {"entidad": "terceros", "modo": "detalle",
             "campos": ["id", "nombre", "es_cliente"],
             "filtros": [{"campo": "nombre", "op": "contiene", "valor": "drogueria"}],
             "limite": 5},
        ),
        (
            "Últimas 5 facturas (detalle)",
            {"entidad": "ventas", "modo": "detalle",
             "campos": ["numero", "fecha", "total", "cliente"],
             "orden": {"campo": "fecha", "dir": "desc"}, "limite": 5},
        ),
        (
            "ATAQUE: pedir 1000 registros crudos (debe quedar acotado a 30)",
            {"entidad": "ventas", "modo": "detalle",
             "campos": ["numero", "total"], "limite": 1000},
        ),
        (
            "ATAQUE: métrica inexistente (debe rechazar)",
            {"entidad": "ventas", "modo": "agregado", "metricas": ["saldo_secreto"]},
        ),
        (
            "ATAQUE: entidad inexistente (debe rechazar)",
            {"entidad": "usuarios_admin", "modo": "agregado", "metricas": ["x"]},
        ),
    ]

    for titulo, consulta in casos:
        print(f"\n{'=' * 70}\n{titulo}\n{'-' * 70}")
        out = await run_semantic_query(consulta)
        print(out[:1500])


if __name__ == "__main__":
    asyncio.run(main())
