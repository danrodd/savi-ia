"""Expresiones SQL compartidas entre entidades del catálogo.

Viven en un solo lugar porque estaban copiadas en tres entidades y se
desincronizaron con el mismo bug en las tres.
"""

from __future__ import annotations


def tercero_display_name(alias: str = "t") -> str:
    """Nombre legible de un tercero: comercial, razón social o persona.

    El ERP guarda los campos vacíos como `''`, no como NULL, así que CADA
    candidato pasa por `NULLIF(TRIM(...), '')`. Sin eso, un `razonSocial`
    vacío detiene el COALESCE y la persona natural queda sin nombre; peor,
    al agrupar por nombre todos esos terceros se funden en una sola fila
    (en frami esa fila sumaba el 61% de la facturación).
    """
    return (
        f"COALESCE(NULLIF(TRIM({alias}.\"nombreComercial\"), ''), "
        f"NULLIF(TRIM({alias}.\"razonSocial\"), ''), "
        f"NULLIF(TRIM(CONCAT_WS(' ', {alias}.\"primerNombre\", "
        f"{alias}.\"primerApellido\")), ''))"
    )
