"""Puesta a punto del esquema de la BD del agente al arrancar.

Una instalación de escritorio no tiene a nadie que corra `alembic
upgrade head` a mano, así que el launcher lo hace solo.

Sobre una BD SQLite **nueva** no reproducimos el historial de
migraciones: fueron autogeneradas contra Postgres y varias no son
portables (la inicial usa `server_default=sa.text('now()')`, que SQLite
no entiende, y `a43047be72dd` referencia `postgresql.JSONB` explícito).
Creamos el esquema desde el metadata y sellamos con `stamp head`, que
deja el mismo resultado. Postgres conserva el camino de siempre.
"""

from __future__ import annotations

import logging

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.base import Base
from app.modules.auth.infrastructure.persistence.models import RefreshTokenModel
from app.modules.company_knowledge.infrastructure.persistence.models import (
    CompanyDocumentBlobModel,
    CompanyDocumentChunkModel,
    CompanyDocumentDatabaseModel,
    CompanyDocumentModel,
)
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.persistence.models import (
    ErpDatabaseModel,
)
from app.modules.free_query.infrastructure.models import AuditQueryModel
from app.modules.llm_providers.infrastructure.persistence.models import (
    LlmProviderConfigModel,
)
from app.paths import resource_dir

logger = logging.getLogger(__name__)

# Importar los modelos es lo que los registra en el metadata de `Base`;
# sin eso `create_all` no crea ninguna tabla. La tupla existe para que el
# import quede referenciado y no lo borre un linter. Mismo conjunto que
# declara `alembic/env.py`.
_REGISTERED_MODELS = (
    ErpDatabaseModel,
    RefreshTokenModel,
    ConversationModel,
    MessageModel,
    AuditQueryModel,
    LlmProviderConfigModel,
    CompanyDocumentModel,
    CompanyDocumentDatabaseModel,
    CompanyDocumentBlobModel,
    CompanyDocumentChunkModel,
)


def _alembic_config() -> Config:
    root = resource_dir()
    config = Config(str(root / "alembic.ini"))
    # En el bundle el cwd es arbitrario, así que el `script_location`
    # relativo del .ini no resolvería.
    config.set_main_option("script_location", str(root / "alembic"))
    # Acá alembic es una biblioteca, no el dueño del proceso: sin esto
    # `env.py` corre `fileConfig()` y le arranca al root logger los
    # handlers que ya montó el launcher, dejando el savi.log del cliente
    # mudo justo antes de que la aplicación empiece a atender peticiones.
    config.attributes["configure_logger"] = False
    return config


def _sqlite_is_fresh(settings: Settings) -> bool:
    """`True` si la BD todavía no tiene esquema.

    Usa el driver sincrónico (`sqlite3` de la stdlib) porque `inspect` y
    `create_all` no aceptan engines async.
    """
    db_path = settings.resolved_agent_db_path
    # El archivo puede no existir, pero su carpeta sí tiene que existir o
    # SQLite falla con "unable to open database file".
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        if "alembic_version" in tables or "conversations" in tables:
            return False
        logger.info("BD del agente vacía: creando esquema desde el metadata.")
        Base.metadata.create_all(engine)
        return True
    finally:
        engine.dispose()


def ensure_schema(settings: Settings) -> None:
    """Deja la BD del agente lista para recibir queries. Idempotente."""
    if settings.agent_db_engine != "sqlite":
        command.upgrade(_alembic_config(), "head")
        return

    if _sqlite_is_fresh(settings):
        command.stamp(_alembic_config(), "head")
    else:
        command.upgrade(_alembic_config(), "head")
