"""Dónde está el ejecutable del CLI de Claude y cómo se lo aísla.

Vive en su propio módulo porque lo necesitan dos lugares que no se pueden
importar entre sí: el launcher del escritorio y el runner del módulo
`chat`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

# Dentro del paquete de npm, el binario real que baja el postinstall.
_NPM_PACKAGE_BINARY = Path("node_modules/@anthropic-ai/claude-code/bin/claude.exe")

# Opciones que aíslan al CLI de la configuración del equipo. Van en TODA
# consulta: el turno, el auto-título y la prueba de credencial.
#
# Sin esto el CLI arranca una sesión completa de Claude Code y carga lo que
# haya en el `~/.claude` de quien instaló SAVI: settings, plugins, hooks, MCP
# servers y skills. Son de otra persona y otro propósito, y entran igual al
# turno. Es el mismo razonamiento que `tools=[]` en el runner —lo que no se
# necesita, no se carga—, más dos motivos propios:
#
# - **Determinismo.** SAVI se comportaría distinto en cada equipo según lo que
#   tenga configurado. Un hook ajeno corriendo dentro de un turno no es un
#   detalle: es código que nadie revisó en el camino de una respuesta.
# - **Tiempo.** Medido en el equipo de desarrollo, con el MCP de SAVI montado
#   y la misma pregunta: 10,88 s → 3,37 s; con una tool de por medio,
#   18,04 s → 9,88 s. Ese arranque se pagaba en CADA turno.
#
# `setting_sources=[]` no toca las credenciales: `local_session` sigue
# autenticando con el `claude login` del equipo, que vive aparte.
# `strict_mcp_config` descarta los MCP servers declarados en archivos; el de
# SAVI se pasa por opciones y no se ve afectado.
ISOLATED_CLI_OPTIONS: dict[str, Any] = {
    "setting_sources": [],
    "strict_mcp_config": True,
}


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
