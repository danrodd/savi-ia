#!/usr/bin/env bash
# Restores a labeled backup and checks out the previous version.
# Usage: ./rollback.sh <label> <previous_git_ref>     e.g. ./rollback.sh 2026-10-14 v1.2.0
# Destructive: recreates both databases. Requires explicit confirmation.
set -euo pipefail
cd "$(dirname "$0")"

LABEL="${1:?usage: ./rollback.sh <label> <previous_git_ref>}"
PREV="${2:?usage: ./rollback.sh <label> <previous_git_ref>}"
set -a; source .env; set +a

for f in "backups/savi-${LABEL}.sql" "backups/cloud-${LABEL}.sql"; do
  [[ -s "$f" ]] || { echo "[ERROR] $f not found" >&2; exit 1; }
done
git -C ../.. rev-parse --verify --quiet "${PREV}^{commit}" >/dev/null \
  || { echo "[ERROR] git ref '${PREV}' does not exist (run: git fetch --tags)" >&2; exit 1; }

echo "This DROPS and recreates '${SAVI_DB_NAME}' and '${CLOUD_DB_NAME}', then checks out ${PREV}."
read -r -p "Type YES to continue: " ans
[[ "$ans" == "YES" ]] || { echo "Aborted."; exit 1; }

docker compose stop savi cloud caddy

restore_database() {   # usage: restore_database DB_NAME OWNER_ROLE DUMP_FILE
  local db="$1" owner="$2" dump="$3"
  docker exec savi-master-db psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"${db}\" WITH (FORCE);" \
    -c "CREATE DATABASE \"${db}\" OWNER \"${owner}\" ENCODING 'UTF8' TEMPLATE template0;"
  docker exec -i savi-master-db psql -U postgres -d "$db" -v ON_ERROR_STOP=1 < "$dump" >/dev/null
  echo "[OK] restored ${db}"
}
restore_database "$SAVI_DB_NAME"  "$SAVI_DB_USER"  "backups/savi-${LABEL}.sql"
restore_database "$CLOUD_DB_NAME" "$CLOUD_DB_USER" "backups/cloud-${LABEL}.sql"

# SAVI files: only if they changed with the upgrade
if [[ -s "backups/data-${LABEL}.tgz" ]]; then
  read -r -p "Also restore data/savi from backup? (yes/no): " d
  if [[ "$d" == "yes" ]]; then rm -rf data/savi && tar xzf "backups/data-${LABEL}.tgz"; fi
fi

# Previous version: detached checkout of the tag, then rebuild images from it.
git -C ../.. checkout --detach "$PREV"
./setup.sh
docker compose up -d --build
docker compose ps
