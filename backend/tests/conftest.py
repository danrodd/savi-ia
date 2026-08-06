"""Configuración base de la suite.

`app/main.py` construye la app al importarse (`app = create_app()`), y
eso lee `Settings`. Sin estos valores, cualquier test que importe
`app.main` falla al recolectar. Se fijan acá — antes que pytest importe
los módulos de test — para que la suite no dependa del `.env` local del
desarrollador.
"""

from __future__ import annotations

import os

os.environ.setdefault("AGENT_DB_ENGINE", "sqlite")
os.environ.setdefault("AGENT_DB_PATH", "tests-placeholder.db")
os.environ.setdefault("ERP_DB_HOST", "localhost")
os.environ.setdefault("ERP_DB_USER", "test")
os.environ.setdefault("ERP_DB_PASSWORD", "test")
os.environ.setdefault("ERP_DB_NAME", "test")
