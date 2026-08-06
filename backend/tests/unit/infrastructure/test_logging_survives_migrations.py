"""`ensure_schema()` corre al arrancar, antes de atender la primera petición.

Si se lleva puesta la configuración de logging, el `savi.log` del cliente
queda mudo desde ahí en adelante y ningún error 500 se registra. Pasó: el
`fileConfig()` de `alembic/env.py` reemplazaba los handlers del root.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import launcher
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.bootstrap import ensure_schema


@pytest.fixture
def isolated_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    root.handlers = []
    try:
        yield
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = previous_handlers
        root.setLevel(previous_level)


@pytest.mark.usefixtures("isolated_root_logger")
def test_log_still_works_after_ensure_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    log_file = tmp_path / "SAVI" / launcher._LOG_FILENAME

    launcher._configure_logging()
    settings = Settings(
        agent_db_engine="sqlite",
        agent_db_path=str(tmp_path / "agente.db"),
        erp_db_host="localhost",
        erp_db_port=5432,
        erp_db_user="u",
        erp_db_password="p",
        erp_db_name="erp",
        jwt_secret="x" * 32,
    )

    ensure_schema(settings)

    # El síntoma real: lo que se loguea DESPUÉS de la migración. Antes de
    # este arreglo, todo esto se perdía.
    logging.getLogger(__name__).info("SAVI escuchando en http://127.0.0.1:8000")
    try:
        raise RuntimeError("fallo al validar credenciales")
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")

    for handler in logging.getLogger().handlers:
        handler.flush()

    contents = log_file.read_text(encoding="utf-8")
    assert "SAVI escuchando en" in contents, (
        "la migración se llevó puesta la configuración de logging"
    )
    assert "RuntimeError: fallo al validar credenciales" in contents
