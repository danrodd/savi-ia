#!/bin/sh
# Aplica migraciones y arranca la API. Con una sola réplica es seguro migrar al arrancar;
# si algún día hay varias, mover `alembic upgrade head` a un paso de despliegue aparte.
set -eu

alembic upgrade head

# --proxy-headers: Caddy es el único que llega a este puerto (no se publica).
exec python -m uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --no-access-log --proxy-headers --forwarded-allow-ips='*'
