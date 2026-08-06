from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import data_dir


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

    # ── BD del agente ────────────────────────────────────────────────────
    # `postgresql` para despliegue servidor; `sqlite` para instalación de
    # escritorio (un solo equipo, sin servidor de BD que administrar). El
    # default conserva el comportamiento previo; el instalador escribe el
    # valor explícito.
    agent_db_engine: Literal["postgresql", "sqlite"] = Field(default="postgresql")
    # Solo para `sqlite`. Vacío (el default) resuelve al directorio de
    # datos del usuario en runtime — ver `resolved_agent_db_path`.
    agent_db_path: str = Field(default="")
    # Solo para `postgresql` — obligatorios en ese modo (ver validador).
    agent_db_host: str | None = Field(default=None)
    agent_db_port: int = Field(default=5432)
    agent_db_user: str | None = Field(default=None)
    agent_db_password: str | None = Field(default=None)
    agent_db_name: str | None = Field(default=None)

    # ── BD del ERP ───────────────────────────────────────────────────────
    # Siempre Postgres y siempre obligatoria: es la fuente de datos que
    # SAVI interpreta, no algo que podamos sustituir por un archivo local.
    erp_db_host: str
    erp_db_port: int = Field(default=5432)
    erp_db_user: str
    erp_db_password: str
    erp_db_name: str
    erp_db_statement_timeout_ms: int = Field(default=60000)

    # ── Autenticación del SDK de Claude ─────────────────────────────────
    # El SDK lanza el CLI `claude` como subproceso y lo autentica con lo
    # primero que encuentre, en este orden: `CLAUDE_CODE_OAUTH_TOKEN`,
    # `ANTHROPIC_API_KEY`, o una sesión ya logueada en el equipo
    # (`claude login`, guardada en ~/.claude/.credentials.json). El token
    # es el método preferido: se genera una vez con `claude setup-token`
    # y no depende de que el cliente administre una clave de API.
    claude_code_oauth_token: str = Field(default="")
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

    # ── Auth ─────────────────────────────────────────────────────────────
    # Secreto para firmar los JWT. NUNCA usar el default en prod.
    jwt_secret: str = Field(default="change-me-in-prod")
    jwt_algorithm: str = Field(default="HS256")
    access_token_ttl_minutes: int = Field(default=15)
    refresh_token_ttl_days: int = Field(default=7)
    # Issuer claim del JWT — útil cuando varios servicios firman.
    jwt_issuer: str = Field(default="savi")

    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000"
    )

    # ── Usage / consumo ──────────────────────────────────────────────────
    # El consumo se ALMACENA siempre en USD (lo que reporta el SDK). Esta
    # tasa es solo para que el frontend muestre el equivalente en COP — no
    # se persiste ni afecta el dato fuente. Ajustable sin redeploy vía .env.
    usd_to_cop_rate: float = Field(default=4000.0)
    # Zona horaria con la que se agrupan los consumos por día. Colombia es
    # UTC-5; agrupar en UTC partiría los días a las 19:00 hora local.
    reporting_timezone: str = Field(default="America/Bogota")

    @model_validator(mode="after")
    def _require_agent_pg_credentials(self) -> "Settings":
        """En modo `postgresql` las credenciales dejan de ser opcionales.

        Son `| None` solo para que el modo `sqlite` no las exija; sin esta
        validación un `.env` mal escrito produciría una URL con `None` y
        el fallo aparecería recién al primer query.
        """
        if self.agent_db_engine != "postgresql":
            return self
        missing = [
            name
            for name in ("agent_db_host", "agent_db_user", "agent_db_password", "agent_db_name")
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError(
                f"agent_db_engine='postgresql' requiere: {', '.join(missing)}. "
                "Usá agent_db_engine='sqlite' para una instalación sin servidor de BD."
            )
        return self

    @property
    def resolved_agent_db_path(self) -> Path:
        """Ruta absoluta del archivo SQLite.

        Si `AGENT_DB_PATH` viene vacío se usa el directorio de datos del
        usuario. El instalador lo deja vacío a propósito: fijar la ruta en
        tiempo de instalación la ata al perfil de quien instaló, que en
        una empresa suele ser una cuenta de administrador distinta de la
        del usuario final.
        """
        if self.agent_db_path.strip():
            return Path(self.agent_db_path).expanduser().resolve()
        return data_dir() / "savi.db"

    @property
    def agent_db_url(self) -> str:
        if self.agent_db_engine == "sqlite":
            # `as_posix()` porque SQLAlchemy interpreta la ruta como parte
            # de una URL: las barras invertidas de Windows se escapan mal.
            return f"sqlite+aiosqlite:///{self.resolved_agent_db_path.as_posix()}"
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
