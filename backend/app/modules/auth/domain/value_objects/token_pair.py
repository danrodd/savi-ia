from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    # TTL del access en segundos — el frontend lo usa para programar
    # el refresh anticipado y evitar 401 innecesarios.
    access_token_expires_in: int
    token_type: str = "Bearer"
