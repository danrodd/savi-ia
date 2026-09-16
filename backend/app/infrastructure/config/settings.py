from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import data_dir

# Valor de fábrica del secreto de firma. Sirve para que `uv run dev` arranque
# sin configurar nada; fuera de `development` se rechaza.
INSECURE_JWT_SECRET = "change-me-in-prod"


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
    # Siempre Postgres. Dejó de ser la fuente de verdad en runtime: es la
    # **semilla** de la base default en la tabla `erp_databases`, que es
    # de donde salen todas las conexiones una vez sembrada. Ver
    # `modules/erp_databases/infrastructure/seed.py`.
    #
    # Por eso pasaron a ser opcionales: una instalación puede registrar su
    # primera base desde la sección de administración sin tocar el `.env`.
    erp_db_host: str = Field(default="")
    erp_db_port: int = Field(default=5432)
    erp_db_user: str = Field(default="")
    erp_db_password: str = Field(default="")
    erp_db_name: str = Field(default="")
    erp_db_statement_timeout_ms: int = Field(default=60000)

    # ── Cifrado de credenciales de conexión al ERP ───────────────────────
    # Clave Fernet (32 bytes en base64 urlsafe) con la que se cifran las
    # contraseñas de `erp_databases`. El instalador genera una al azar por
    # instalación, igual que `JWT_SECRET`.
    #
    # NO se reutiliza `JWT_SECRET`: rotar el de JWT solo invalida sesiones
    # (molesto pero inofensivo), rotar el de credenciales deja ilegibles
    # todas las contraseñas guardadas. Mezclarlos convierte una operación
    # rutinaria en una pérdida de datos.
    erp_credentials_key: str = Field(default="")
    # Clave anterior durante una rotación: se descifra con ambas y se
    # cifra con la nueva. Vacía fuera de una rotación.
    erp_credentials_key_old: str = Field(default="")
    # Tope de engines del ERP vivos a la vez (evicción LRU del registry).
    erp_max_open_engines: int = Field(default=10)

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

    # Resiliencia de Gemini antes de emitir texto visible.
    gemini_retry_attempts: int = Field(default=3)
    gemini_retry_base_delay_s: float = Field(default=0.5)
    gemini_fallback_models: str = Field(default="gemini-3.1-flash-lite,gemini-flash-lite-latest")

    # Resiliencia de OpenAI: mismo patrón que Gemini, sin fallback cruzado.
    # Arranca vacío a propósito: un modelo fallback debe elegirlo una persona.
    openai_retry_attempts: int = Field(default=3)
    openai_retry_base_delay_s: float = Field(default=0.5)
    openai_fallback_models: str = Field(default="")

    # ── Free SQL query (Nivel D) ─────────────────────────────────────────
    # Tope absoluto de filas devueltas por consulta libre del LLM.
    free_query_max_rows: int = Field(default=50)
    # EXPLAIN gate: si el planner estima más que esto, rechazamos antes
    # de ejecutar.
    free_query_max_estimated_rows: int = Field(default=1000)

    # ── Conocimiento de la empresa (documentos propios) ──────────────────
    # Límites de carga por archivo y por documento.
    company_docs_max_file_mb: int = Field(default=20)
    company_docs_max_pages: int = Field(default=500)
    company_docs_max_chunks_per_doc: int = Field(default=2000)
    # Tope de la instalación. El worker lo verifica antes de guardar.
    company_docs_max_total_chunks: int = Field(default=50000)
    # Fragmentación: tamaño objetivo y solapamiento en tokens estimados
    # (caracteres ÷ 4). Los ajusta el spike del modelo.
    company_docs_chunk_tokens: int = Field(default=900)
    company_docs_chunk_overlap: int = Field(default=120)
    # Modelo de embeddings. e5 usa prefijos `query:`/`passage:`; el
    # embedder los aplica solo cuando el nombre del modelo contiene `e5`.
    company_docs_embedding_model: str = Field(default="intfloat/multilingual-e5-small")
    # Vacío = ubicación por entorno (modelo empaquetado en la app, o
    # `backend/.models/` en desarrollo). Ver `resolve_model_dir`.
    company_docs_model_dir: str = Field(default="")
    # Apaga el worker de ingesta (tests). En runtime siempre `true`.
    company_docs_worker_enabled: bool = Field(default=True)
    # Búsqueda híbrida (Fase 2). `min_similarity` depende del modelo: e5
    # comprime los cosenos en 0.78-0.87. Fijado por el spike
    # (docs/company_knowledge/spike-modelo.md): 0.80 conserva todas las
    # respuestas del set; 0.82 perdía una paráfrasis sin coincidencia léxica.
    # Solo recorta ruido: ningún umbral separa las preguntas sin respuesta.
    company_docs_min_similarity: float = Field(default=0.80)
    company_docs_search_candidates: int = Field(default=50)
    company_docs_search_limit: int = Field(default=6)
    company_docs_search_max_per_document: int = Field(default=3)
    company_docs_max_context_chars: int = Field(default=6000)

    # ── Auth ─────────────────────────────────────────────────────────────
    # Secreto para firmar los JWT. Fuera de `development` el default hace
    # fallar el arranque: quien lo conozca puede firmarse un token de
    # administrador. Ver `_reject_default_jwt_secret`.
    jwt_secret: str = Field(default=INSECURE_JWT_SECRET)
    jwt_algorithm: str = Field(default="HS256")
    access_token_ttl_minutes: int = Field(default=15)
    refresh_token_ttl_days: int = Field(default=7)
    # Issuer claim del JWT — útil cuando varios servicios firman.
    jwt_issuer: str = Field(default="savi")

    # Códigos de usuario que reciben la sección de administración de SAVI
    # aunque el ERP no los marque como `administrador`. Vacío por default.
    #
    # Alcance limitado a propósito: SOLO habilita esa sección. No otorga
    # módulos del ERP ni cambia qué datos puede consultar el usuario —
    # administrar conexiones y tener acceso a datos son cosas distintas.
    savi_admin_logins: str = Field(default="")

    cors_allowed_origins: str = Field(default="http://localhost:5173,http://localhost:3000")

    # ── Límites de pedidos ───────────────────────────────────────────────
    # Defaults holgados a propósito: un usuario de la app de escritorio no
    # los toca nunca, y frenan a un script. Medido antes de ponerlos: 50
    # logins fallidos en paralelo se procesaban todos.
    rate_limit_enabled: bool = Field(default=True)
    # Login, por código de usuario: es el que frena la fuerza bruta contra
    # una cuenta concreta.
    rate_limit_login_per_minute: int = Field(default=10)
    # Login, por IP: mucho más holgado a propósito. Una oficina entera sale
    # por una sola IP detrás de NAT, así que un límite bajo acá no frena a un
    # atacante (que rota IP) y sí deja afuera a diez compañeros entrando a la
    # misma hora. Su trabajo es cortar el barrido de muchas cuentas desde un
    # mismo origen, no proteger una cuenta puntual.
    rate_limit_login_per_minute_per_ip: int = Field(default=60)
    # Contraseñas malas seguidas antes de bloquear ese login. Las claves del
    # ERP son MD5 sin sal: la ventana sola no frena un ataque lento.
    rate_limit_login_max_failures: int = Field(default=5)
    rate_limit_login_block_minutes: int = Field(default=15)
    rate_limit_refresh_per_minute: int = Field(default=30)
    # Chat: por usuario. Cada turno cuesta dinero de verdad.
    rate_limit_chat_per_minute: int = Field(default=20)
    rate_limit_chat_per_hour: int = Field(default=200)
    rate_limit_upload_per_hour: int = Field(default=30)
    # Techo general por IP, para todo lo demás (incluye `/health`).
    rate_limit_global_per_minute: int = Field(default=300)
    # Solo se confía en `X-Forwarded-For` si hay un proxy declarado. Confiarlo
    # siempre vuelve decorativo el límite: cualquiera falsea el header.
    trust_proxy_headers: bool = Field(default=False)

    # ── Concurrencia del chat ────────────────────────────────────────────
    # Cada turno con Claude levanta un subproceso del CLI con su contexto.
    # Sin tope, N usuarios simultáneos son N procesos y la máquina se queda
    # sin memoria antes de que termine ninguno.
    max_concurrent_chat_turns: int = Field(default=3)
    # Reloj de pared por turno. `max_agent_turns` acota las rondas de
    # herramienta, no el tiempo: un turno podía quedarse colgado reteniendo
    # el subproceso y la conexión SSE.
    chat_turn_timeout_seconds: float = Field(default=180.0)

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

    @model_validator(mode="after")
    def _require_postgres_outside_development(self) -> "Settings":
        """SQLite no aguanta varios usuarios a la vez.

        Un turno de chat mantiene una transacción abierta mientras el modelo
        responde, y las escrituras internas compiten con ese lock: el propio
        `pool.py` documenta que forzar `BEGIN IMMEDIATE` convirtió una carrera
        ocasional en un fallo garantizado de 30 s por turno.

        Para la app de escritorio (un usuario, una máquina) está bien y sigue
        siendo el default. Para un despliegue servidor, no.
        """
        if self.app_env != "development" and self.agent_db_engine == "sqlite":
            raise ValueError(
                "AGENT_DB_ENGINE='sqlite' no soporta varios usuarios simultáneos: "
                "un turno de chat retiene la transacción mientras el modelo responde. "
                "Usá 'postgresql' fuera de desarrollo, o APP_ENV='development' si es "
                "una instalación de escritorio de un solo usuario."
            )
        return self

    @model_validator(mode="after")
    def _reject_default_jwt_secret(self) -> "Settings":
        """El secreto de fábrica firma tokens válidos para cualquiera que lo
        conozca, incluido `is_admin`. En desarrollo es una comodidad; en
        cualquier otro entorno es una puerta abierta, así que no arranca."""
        if self.app_env != "development" and self.jwt_secret.strip() == INSECURE_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET tiene el valor de fábrica y APP_ENV no es 'development'. "
                "Generá uno nuevo (por ejemplo con "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"`) '
                "y guardalo en el .env antes de usar SAVI."
            )
        return self

    @property
    def uses_insecure_jwt_secret(self) -> bool:
        """Para avisar por log en desarrollo sin repetir la constante."""
        return self.jwt_secret.strip() == INSECURE_JWT_SECRET

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
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def savi_admin_logins_set(self) -> frozenset[str]:
        """Códigos normalizados a mayúsculas, igual que los del ERP."""
        return frozenset(
            code.strip().upper() for code in self.savi_admin_logins.split(",") if code.strip()
        )

    @property
    def gemini_fallback_models_list(self) -> tuple[str, ...]:
        """Return non-empty fallback IDs, preserving order and uniqueness."""
        return tuple(
            dict.fromkeys(
                model.strip() for model in self.gemini_fallback_models.split(",") if model.strip()
            )
        )

    @property
    def openai_fallback_models_list(self) -> tuple[str, ...]:
        """Return non-empty fallback IDs, preserving order and uniqueness."""
        return tuple(
            dict.fromkeys(
                model.strip() for model in self.openai_fallback_models.split(",") if model.strip()
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
