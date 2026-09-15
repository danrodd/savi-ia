"""Configuración base de la suite.

`app/main.py` construye la app al importarse (`app = create_app()`), y
eso lee `Settings`. Sin estos valores, cualquier test que importe
`app.main` falla al recolectar. Se fijan acá — antes que pytest importe
los módulos de test — para que la suite no dependa del `.env` local del
desarrollador.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("AGENT_DB_ENGINE", "sqlite")
os.environ.setdefault("AGENT_DB_PATH", "tests-placeholder.db")
os.environ.setdefault("ERP_DB_HOST", "localhost")
os.environ.setdefault("ERP_DB_USER", "test")
os.environ.setdefault("ERP_DB_PASSWORD", "test")
os.environ.setdefault("ERP_DB_NAME", "test")
# Clave Fernet fija para la suite: los tests que ejercitan el cifrado
# generan la suya cuando necesitan una distinta.
os.environ.setdefault("ERP_CREDENTIALS_KEY", "sIYQBhcJUxE6vsRRrJvVKa3CtoUj_o8SPDBSAcHDCyM=")


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """Los límites de pedidos son un singleton de proceso.

    Sin esto, un test que hace muchos pedidos deja contadores cargados y el
    siguiente empieza cerca del tope: fallos intermitentes que dependen del
    orden de ejecución. Se limpia en lugar de desactivar el límite, así los
    tests siguen ejercitando el camino real.
    """
    from app.modules.chat.infrastructure.http import concurrency
    from app.shared.rate_limit import get_rate_limiter

    get_rate_limiter().reset()
    concurrency.reset_for_tests()
