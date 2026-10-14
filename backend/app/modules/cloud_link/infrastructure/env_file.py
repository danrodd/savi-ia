"""Limpieza segura de una variable del `.env`.

El token de vinculación es de un solo uso, pero no tiene por qué quedar en
disco una vez canjeado. Se reescribe la línea a vacío (`CLAVE=`) y se deja el
resto del archivo intacto, saltos de línea incluidos. Si el archivo no se
puede escribir (SAVI corre sin privilegios sobre Program Files) solo se
loguea: no es un error de la vinculación.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def clear_env_variable(env_path: Path, key: str) -> bool:
    """Deja `key=` vacía. `True` si no queda valor (o no había nada que
    limpiar); `False` si el archivo no se pudo leer o escribir."""
    try:
        original = env_path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return True
    except (OSError, UnicodeDecodeError):
        logger.warning("No se pudo leer %s para limpiar %s.", env_path.name, key)
        return False

    prefix = f"{key}="
    changed = False
    lines: list[str] = []
    for line in original.splitlines(keepends=True):
        body = line.lstrip("﻿")
        if body.lstrip().startswith(prefix):
            value = body.strip()[len(prefix) :]
            if value:
                newline = line[len(line.rstrip("\r\n")) :]
                bom = "﻿" if line.startswith("﻿") else ""
                line = f"{bom}{prefix}{newline}"
                changed = True
        lines.append(line)

    if not changed:
        return True
    try:
        env_path.write_bytes("".join(lines).encode("utf-8"))
    except OSError:
        logger.warning(
            "No se pudo escribir %s: el token de SAVI Cloud quedó en el archivo. "
            "Ya fue canjeado y no sirve; se puede borrar a mano.",
            env_path.name,
        )
        return False
    return True
