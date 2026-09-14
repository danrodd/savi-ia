"""Variables de entorno con las que se lanza el CLI de Claude.

Se pasan por `ClaudeAgentOptions(env=...)` en **cada** consulta, no por
`os.environ`: así, cambiar la credencial desde administración aplica al
turno siguiente sin reiniciar. El SDK mezcla `os.environ` con `env` y
`env` gana.

Vive en `app/infrastructure` porque lo usan el runner del chat, el
generador de títulos y la prueba de credencial del módulo
`llm_providers`, que no se pueden importar entre sí.
"""

from __future__ import annotations

import os

API_KEY_VAR = "ANTHROPIC_API_KEY"
OAUTH_TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
GIT_BASH_VAR = "CLAUDE_CODE_GIT_BASH_PATH"

_CREDENTIAL_VARS = {"api_key": API_KEY_VAR, "oauth_token": OAUTH_TOKEN_VAR}


def build_claude_env(
    *,
    credential_kind: str,
    credential: str | None,
    git_bash_path: str = "",
) -> dict[str, str]:
    """El `env` del CLI para esta credencial.

    Con `local_session` no se inyecta credencial: el CLI usa su propio
    `claude login`. Una variable de credencial heredada del proceso que no
    corresponde a la elegida se pisa con vacío; si no, el CLI la tomaría
    antes que la configurada.
    """
    env: dict[str, str] = {}
    chosen = _CREDENTIAL_VARS.get(credential_kind)
    for var in _CREDENTIAL_VARS.values():
        if var == chosen and credential:
            env[var] = credential
        elif os.environ.get(var):
            env[var] = ""
    if git_bash_path:
        env[GIT_BASH_VAR] = git_bash_path
    return env
