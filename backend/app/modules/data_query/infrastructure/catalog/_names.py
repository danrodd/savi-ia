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


def tercero_full_name(alias: str = "t") -> str:
    """Nombre del tercero como lo muestra el ERP en sus documentos.

    `nombreCompleto` es la razón social o, para una persona, apellidos y
    nombres completos ("DIAZ TORRES DELIA MARI"). Medido el 2026-11-25: nunca
    está vacío en imporllantas ni en frami. Mostrar solo el nombre comercial
    ("DELIA DIAZ") hacía creer al usuario que se hablaba de otra persona.
    """
    return f"COALESCE(NULLIF(TRIM({alias}.\"nombreCompleto\"), ''), {tercero_display_name(alias)})"


def tercero_search_text(alias: str = "t") -> str:
    """Texto donde se busca un tercero por nombre: comercial, completo y razón social.

    `contiene` exige que cada palabra aparezca. Buscando solo en el nombre
    corto (comercial, o primer nombre y primer apellido), "José Manuel
    Rodríguez" no encontraba a quien tiene ese segundo nombre, y "Delia Díaz
    Torres" no encontraba a quien figura como "DELIA DIAZ".
    """
    return (
        f'CONCAT_WS(\' \', {alias}."nombreComercial", {alias}."nombreCompleto", '
        f'{alias}."razonSocial", {alias}."primerNombre", {alias}."segundoNombre", '
        f'{alias}."primerApellido", {alias}."segundoApellido")'
    )


def product_search_text(alias: str = "p") -> str:
    """Texto donde se busca un producto: la descripción y el código.

    El usuario nombra el producto por su referencia ("LLANTAS0183") tanto como
    por su descripción. En la prueba con un cliente, el modelo buscó la
    referencia en la descripción y respondió que no había ventas.
    """
    return f"(COALESCE({alias}.\"descripcion\", '') || ' ' || COALESCE({alias}.\"codigo\", ''))"
