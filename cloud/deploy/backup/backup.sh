#!/bin/sh
# Backup periódico de Postgres con pg_dump (formato custom, comprimido).
# Corre en bucle dentro del contenedor: un dump al arrancar y luego cada
# BACKUP_INTERVAL_HOURS. Conserva BACKUP_KEEP_DAYS días. Variables PG* vienen de Compose.
set -eu

KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
DEST=/backups

while true; do
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    file="${DEST}/savi_cloud_${stamp}.dump"
    if pg_dump --format=custom --file="${file}.part"; then
        mv "${file}.part" "${file}"
        echo "backup ok: ${file}"
    else
        rm -f "${file}.part"
        echo "backup FALLIDO: ${stamp}" >&2
    fi
    find "${DEST}" -name 'savi_cloud_*.dump' -mtime "+${KEEP_DAYS}" -delete
    sleep "$((INTERVAL_HOURS * 3600))"
done
