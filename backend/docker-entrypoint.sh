#!/bin/sh
# Arranque de SAVI en contenedor.
#
# 1. Carga los secretos: cada variable `NOMBRE_FILE=/run/secrets/x` se exporta como `NOMBRE`
#    con el contenido del archivo. Así ningún valor secreto aparece en `docker inspect`, en el
#    compose ni en el `.env` (guía de despliegue, §5).
# 2. Falla fuerte si falta un secreto obligatorio, en vez de arrancar a medias.
# 3. Arranca uvicorn con UN worker: el registry de engines del ERP, el índice de documentos y
#    los límites de pedidos viven en la memoria del proceso. Las migraciones corren en el
#    arranque de la aplicación (`ensure_schema`).
set -eu

load_file_secrets() {
    for name in $(env | sed -n 's/^\([A-Z0-9_]*\)_FILE=.*/\1/p'); do
        file_var="${name}_FILE"
        path="$(printenv "$file_var")"
        if [ ! -r "$path" ]; then
            echo "[ERROR] $file_var apunta a '$path', que no existe o no se puede leer." >&2
            exit 1
        fi
        # `$(cat ...)` recorta saltos de línea finales; no se imprime el valor.
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

for required in JWT_SECRET ERP_CREDENTIALS_KEY AGENT_DB_PASSWORD; do
    if [ -z "$(printenv "$required")" ]; then
        echo "[ERROR] Falta $required (definí ${required}_FILE en el compose)." >&2
        exit 1
    fi
done

# Con argumentos ejecuta ese comando con el entorno ya resuelto (diagnóstico, tareas de
# administración): `docker compose exec savi /app/docker-entrypoint.sh python -m app.cli ...`.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --no-access-log
