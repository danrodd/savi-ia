"""Configuración tipada, validada al arrancar. Variables con prefijo `CLOUD_`."""

from __future__ import annotations

from datetime import datetime
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
    # Semilla de la consola del staff (firma de sesiones y cifrado de secretos TOTP).
    # Generar con: openssl rand -hex 32. Vacía = consola deshabilitada (503).
    console_secret: str = ""
    # La cookie de refresh solo viaja por HTTPS; se apaga únicamente en desarrollo local.
    console_cookie_secure: bool = True
    # Última versión publicada de SAVI (p. ej. v1.3.0): define "instancia desactualizada".
    latest_version: str = ""
    # Cuándo se publicó `latest_version`: sin esta fecha no se alerta por desactualización.
    latest_version_published_at: datetime | None = None
    # Cada cuántos segundos se evalúan las alertas (0 = apagado).
    alerts_interval_seconds: float = Field(default=300, ge=0)

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if not self.database_url:
            raise ValueError("CLOUD_DATABASE_URL es obligatoria")
        if self.console_secret and len(self.console_secret) < 32:
            raise ValueError("CLOUD_CONSOLE_SECRET debe tener al menos 32 caracteres")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
