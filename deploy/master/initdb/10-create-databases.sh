#!/bin/sh
# Crea los roles y las bases de SAVI y de SAVI Cloud la PRIMERA vez que se inicializa el volumen
# de PostgreSQL (la imagen oficial ejecuta este directorio solo con el volumen vacío).
#
# Cada aplicación tiene su propio rol, dueño de su propia base: SAVI no puede leer las tablas
# de Cloud ni al revés. La contraseña la lee el propio psql desde el archivo (`\set pw `cat ...``):
# nunca pasa por la línea de comandos de ningún proceso, donde `ps` la mostraría.
set -eu

create_role_and_database() {
    role="$1"
    database="$2"
    password_file="$3"

    if [ ! -r "$password_file" ]; then
        echo "[ERROR] No se puede leer el secreto $password_file" >&2
        exit 1
    fi

    # Heredoc SIN comillas a propósito: solo se expande ${password_file}. El resto del SQL no
    # lleva `$` ni comillas invertidas.
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
        -v role="$role" -v database="$database" <<SQL
\set pw \`cat "${password_file}"\`
CREATE ROLE :"role" LOGIN PASSWORD :'pw';
CREATE DATABASE :"database" OWNER :"role" ENCODING 'UTF8' TEMPLATE template0;
SQL
}

create_role_and_database "$SAVI_DB_USER" "$SAVI_DB_NAME" "$SAVI_DB_PASSWORD_FILE"
create_role_and_database "$CLOUD_DB_USER" "$CLOUD_DB_NAME" "$CLOUD_DB_PASSWORD_FILE"
echo "[OK] Bases creadas: $SAVI_DB_NAME y $CLOUD_DB_NAME"
