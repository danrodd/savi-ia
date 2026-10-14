"""Configuración tipada, validada al arrancar. Variables con prefijo `CLOUD_`."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLOUD_", env_file=".env", extra="ignore")

    env: Literal["development", "production", "test"] = "production"
    # postgresql+asyncpg://usuario:clave@host:5432/base
    database_url: str = ""
    log_level: str = "INFO"
    # CORS cerrado por defecto: la API la consumen instancias (servidor a servidor) y,
    # en la Fase 3, la consola; solo ahí se agregan orígenes. Formato JSON:
    # CLOUD_CORS_ORIGINS='["https://consola.ejemplo.com"]'
    cors_origins: list[str] = Field(default_factory=list)
    enrollment_token_ttl_hours: int = Field(default=72, ge=1, le=24 * 365)

    @model_validator(mode="after")
    def _require_database_url(self) -> Settings:
        if not self.database_url:
            raise ValueError("CLOUD_DATABASE_URL es obligatoria")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
