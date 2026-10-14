#!/usr/bin/env bash
# Backs up both databases, the SAVI data and (optionally) .env + secrets.
# Usage: ./backup.sh [label]     (default label: current date)
#
# IMPORTANT: secrets/erp_credentials_key.txt is part of the backup on purpose. Without it the
# ERP passwords stored in the database cannot be decrypted, and the dump is useless.
set -euo pipefail
cd "$(dirname "$0")"

LABEL="${1:-$(date +%F)}"
mkdir -p backups && chmod 700 backups
set -a; source .env; set +a

dump_database() {   # usage: dump_database DB_NAME OUTPUT_FILE
  local db="$1" out="$2" tmp="backups/.tmp.sql"
  # Write to a temp file and move only if it finished (a failed dump never replaces a good one).
  if docker exec savi-master-db pg_dump -U postgres -d "$db" > "$tmp" && [[ -s "$tmp" ]]; then
    mv "$tmp" "$out"
  else
    rm -f "$tmp"; echo "[ERROR] dump of '$db' failed" >&2; exit 1
  fi
  # A complete PostgreSQL dump ends with this marker.
  tail -n1 "$out" | grep -q 'PostgreSQL database dump complete' \
    || { echo "[ERROR] dump of '$db' looks incomplete" >&2; exit 1; }
  echo "[OK] $out"
}

# 1) Databases
dump_database "$SAVI_DB_NAME"  "backups/savi-${LABEL}.sql"
dump_database "$CLOUD_DB_NAME" "backups/cloud-${LABEL}.sql"

# 2) SAVI files (Claude CLI state and logs)
tar czf "backups/data-${LABEL}.tgz" data/savi
echo "[OK] backups/data-${LABEL}.tgz"

# 3) Config and secrets copy (sensitive: keep chmod 700 and move off the server)
cp .env "backups/.env.${LABEL}"
cp -r secrets "backups/secrets.${LABEL}"
chmod -R go-rwx backups

echo "[OK] Backup '${LABEL}' written to backups/. Copy it OFF the server."
echo "     Keep at least 7 days and test a restore periodically."
