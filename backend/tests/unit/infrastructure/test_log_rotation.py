"""El log del cliente es la única evidencia cuando algo falla en su equipo.

Si crece sin techo deja de servir justo cuando hace falta abrirlo, así que
el tope y la rotación se verifican, no se asumen.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import launcher


@pytest.fixture
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirige `data_dir()` a un temporal y restaura el logging global.

    `basicConfig` toca el root logger del proceso; sin restaurarlo, este
    test se llevaría puesta la salida del resto de la suite.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    root.handlers = []
    try:
        yield tmp_path / "SAVI"
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = previous_handlers
        root.setLevel(previous_level)


def test_rotates_instead_of_growing_forever(log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_LOG_MAX_BYTES", 2048)
    monkeypatch.setattr(launcher, "_LOG_BACKUPS", 2)

    launcher._configure_logging()
    logger = logging.getLogger("uvicorn.access")
    for i in range(400):
        logger.info('127.0.0.1 - "POST /auth/login HTTP/1.1" 500 (linea %d)', i)

    for handler in logging.getLogger().handlers:
        handler.flush()

    active = log_dir / launcher._LOG_FILENAME
    assert active.is_file()
    # El techo es por archivo: el handler rota *antes* de pasarse, así que
    # el activo puede quedar apenas por debajo pero nunca desbordado.
    assert active.stat().st_size <= 2048

    backups = sorted(p.name for p in log_dir.glob(f"{launcher._LOG_FILENAME}.*"))
    assert backups == [f"{launcher._LOG_FILENAME}.1", f"{launcher._LOG_FILENAME}.2"], (
        "sin rotación el archivo activo crecería sin límite y no habría respaldos"
    )


def test_uvicorn_tracebacks_reach_the_file(log_dir: Path) -> None:
    """Un 500 tiene que quedar registrado con su stack.

    uvicorn corre con `log_config=None`, así que no instala handlers
    propios y sus loggers propagan a este root. Si algún día se le pasa un
    `log_config`, este test avisa: el traceback dejaría de llegar al
    archivo y soporte se quedaría sin la única pista que tiene.
    """
    launcher._configure_logging()

    try:
        raise RuntimeError("fallo al validar credenciales")
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")

    for handler in logging.getLogger().handlers:
        handler.flush()

    contents = (log_dir / launcher._LOG_FILENAME).read_text(encoding="utf-8")
    assert "Exception in ASGI application" in contents
    assert "RuntimeError: fallo al validar credenciales" in contents
    assert "Traceback (most recent call last)" in contents
