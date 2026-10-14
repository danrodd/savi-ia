#!/bin/sh
# Arranque de SAVI Cloud en contenedor.
#
# 1. Carga los secretos: cada `NOMBRE_FILE=/run/secrets/x` se exporta como `NOMBRE`. Ningún valor
#    secreto aparece en `docker inspect`, en el compose ni en el `.env`.
# 2. Arma `CLOUD_DATABASE_URL` desde sus partes (la contraseña llega por archivo y se codifica
#    para URL), salvo que ya venga completa.
# 3. Sin argumentos aplica migraciones y arranca la API; con argumentos ejecuta ese comando. Con
#    una sola réplica es seguro migrar al arrancar; si algún día hay varias, mover
#    `alembic upgrade head` a un paso de despliegue aparte.
set -eu

load_file_secrets() {
    for name in $(env | sed -n 's/^\([A-Z0-9_]*\)_FILE=.*/\1/p'); do
        file_var="${name}_FILE"
        path="$(printenv "$file_var")"
        if [ ! -r "$path" ]; then
            echo "[ERROR] $file_var apunta a '$path', que no existe o no se puede leer." >&2
            exit 1
        fi
        value="$(cat "$path")"
        if [ -z "$value" ]; then
            echo "[ERROR] El secreto de $file_var está vacío." >&2
            exit 1
        fi
        export "$name=$value"
        unset "$file_var"
    done
}

load_file_secrets

if [ -z "${CLOUD_DATABASE_URL:-}" ]; then
    for required in CLOUD_DB_HOST CLOUD_DB_USER CLOUD_DB_NAME CLOUD_DB_PASSWORD; do
        if [ -z "$(printenv "$required")" ]; then
            echo "[ERROR] Falta $required (o definí CLOUD_DATABASE_URL completa)." >&2
            exit 1
        fi
    done
    CLOUD_DATABASE_URL="$(python - <<'PY'
import os
from urllib.parse import quote

user = quote(os.environ["CLOUD_DB_USER"], safe="")
password = quote(os.environ["CLOUD_DB_PASSWORD"], safe="")
host = os.environ["CLOUD_DB_HOST"]
port = os.environ.get("CLOUD_DB_PORT", "5432")
name = os.environ["CLOUD_DB_NAME"]
print(f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}")
PY
)"
    export CLOUD_DATABASE_URL
    unset CLOUD_DB_PASSWORD
fi

# Con argumentos ejecuta ese comando con el entorno ya resuelto (secretos y URL de la base), sin
# migrar ni levantar la API. Es lo que usa `docker compose exec cloud /app/docker-entrypoint.sh
# cloud-admin ...`: un `exec` directo no ve las variables que arma este script.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

alembic upgrade head

# --proxy-headers: Caddy es el único que llega a este puerto (no se publica).
exec python -m uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --no-access-log --proxy-headers --forwarded-allow-ips='*'
