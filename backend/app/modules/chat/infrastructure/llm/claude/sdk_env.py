"""Credenciales y entorno del CLI de Claude.

El SDK lanza el binario `claude` como subproceso; en Windows necesita
`CLAUDE_CODE_GIT_BASH_PATH` apuntando a `bash.exe`.
"""

import os

from app.infrastructure.config import Settings


def apply_sdk_env(settings: Settings) -> None:
    if settings.claude_code_oauth_token:
        os.environ.setdefault("CLAUDE_CODE_OAUTH_TOKEN", settings.claude_code_oauth_token)
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.claude_code_git_bash_path:
        os.environ.setdefault("CLAUDE_CODE_GIT_BASH_PATH", settings.claude_code_git_bash_path)
