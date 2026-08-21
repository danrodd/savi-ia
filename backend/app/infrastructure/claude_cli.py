"""Dónde está el ejecutable del CLI de Claude.

Vive en su propio módulo porque lo necesitan dos lugares que no se pueden
importar entre sí: el launcher del escritorio y el runner del módulo
`chat`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Dentro del paquete de npm, el binario real que baja el postinstall.
_NPM_PACKAGE_BINARY = Path("node_modules/@anthropic-ai/claude-code/bin/claude.exe")


def resolve_cli_path() -> str | None:
    """La ruta del CLI, prefiriendo el ejecutable real sobre el shim de npm.

    npm no instala un ejecutable: instala `claude.cmd`, un archivo por
    lotes que reenvía al binario del paquete. Pasar por ese shim mete a
    cmd.exe en el medio, y cmd.exe corta la línea de comandos en 8191
    caracteres. El SDK manda el system prompt por argv y el de SAVI mide
    17.146, así que cada turno moría con "La línea de comandos es
    demasiado larga" y código 1.

    Con el instalador nativo del CLI el problema no existe —deja un .exe
    de verdad—, y por eso no aparecía ni en desarrollo ni en los equipos
    donde alguien ya venía usando Claude Code.

    Si el binario no está, se devuelve lo que haya: peor que hoy no puede
    quedar, y el diagnóstico avisa.
    """
    found = shutil.which("claude")
    if found is None:
        return None
    path = Path(found)
    if path.suffix.lower() != ".cmd":
        return found
    real = path.parent / _NPM_PACKAGE_BINARY
    return str(real) if real.is_file() else found
