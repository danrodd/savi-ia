"""Proveedores de IA soportados y formas de autenticarse contra ellos."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderKind(StrEnum):
    CLAUDE = "claude"
    GEMINI = "gemini"


class CredentialKind(StrEnum):
    API_KEY = "api_key"  # Claude y Gemini
    OAUTH_TOKEN = "oauth_token"  # solo Claude (CLAUDE_CODE_OAUTH_TOKEN)
    # Solo Claude: la sesión de `claude login` del equipo. No guarda nada.
    LOCAL_SESSION = "local_session"


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Precio de un modelo en USD por millón de tokens."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    display_name: str
