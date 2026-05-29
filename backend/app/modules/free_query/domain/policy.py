"""Política de ejecución de SQL libre.

Constantes ajustables que definen los límites técnicos. Si en el futuro
hay que aflojar/apretar, todo se cambia desde acá (no esparcir mágicos
por el código).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FreeQueryPolicy:
    # Tope de filas devueltas — se aplica como LIMIT en el SQL y como cap
    # post-ejecución (por si la BD igual devuelve más).
    max_rows: int = 50

    # EXPLAIN gate: si el planner estima más filas que esto, rechazo.
    max_estimated_rows: int = 1000

    # Profundidad máxima de subqueries anidadas. > 2 es señal de
    # complejidad sospechosa o intento de evasión.
    max_subquery_depth: int = 2

    # Cuántos chars de SQL aceptamos como input (el LLM no necesita más).
    max_sql_length: int = 4000


DEFAULT_POLICY = FreeQueryPolicy()
