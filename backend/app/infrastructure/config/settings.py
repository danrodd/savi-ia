from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="SAVI")
    app_env: Literal["development", "staging", "production"] = Field(default="development")
    app_debug: bool = Field(default=False)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    agent_db_host: str
    agent_db_port: int = Field(default=5432)
    agent_db_user: str
    agent_db_password: str
    agent_db_name: str

    erp_db_host: str
    erp_db_port: int = Field(default=5432)
    erp_db_user: str
    erp_db_password: str
    erp_db_name: str
    erp_db_statement_timeout_ms: int = Field(default=60000)

    anthropic_api_key: str = Field(default="")
    claude_model: str = Field(default="claude-sonnet-4-6")
    # Modelo dedicado a generación de títulos (tareas one-shot baratas).
    # Haiku 4.5 cuesta ~10× menos que Sonnet y rinde bien para resumir
    # una conversación en ≤5 palabras.
    claude_title_model: str = Field(default="claude-haiku-4-5")
    claude_code_git_bash_path: str = Field(default="")
    max_response_chars: int = Field(default=20000)
    max_agent_turns: int = Field(default=40)
    # Timeout corto para la fase 2 del título inline al cierre del turno.
    # Si tarda más, dejamos el de la fase 1 (que ya está en BD) y seguimos.
    title_phase2_timeout_s: float = Field(default=4.0)

    # ── Free SQL query (Nivel D) ─────────────────────────────────────────
    # Tope absoluto de filas devueltas por consulta libre del LLM.
    free_query_max_rows: int = Field(default=50)
    # EXPLAIN gate: si el planner estima más que esto, rechazamos antes
    # de ejecutar.
    free_query_max_estimated_rows: int = Field(default=1000)

    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000"
    )

    @property
    def agent_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.agent_db_user}:{self.agent_db_password}"
            f"@{self.agent_db_host}:{self.agent_db_port}/{self.agent_db_name}"
        )

    @property
    def erp_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.erp_db_user}:{self.erp_db_password}"
            f"@{self.erp_db_host}:{self.erp_db_port}/{self.erp_db_name}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
