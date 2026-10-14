#!/usr/bin/env bash
# Prepares the SAVI Master deployment: .env, directories, secrets and version stamp.
# Idempotent: safe to run many times. Never overwrites or prints a secret.
set -euo pipefail

cd "$(dirname "$0")"

# Secrets generated automatically (file names without .txt). Alphanumeric, 48 chars.
AUTO_SECRETS=(db_root_password savi_db_password cloud_db_password)
# Long random secrets (64 chars).
LONG_SECRETS=(jwt_secret cloud_console_secret)
# Secrets the operator must create by hand (external credentials). None today: the AI provider
# keys are configured from the SAVI administration screen and stored encrypted.
MANUAL_SECRETS=()

# The container user (backend/Dockerfile) owns the SAVI data directories.
SAVI_UID=10001
SAVI_GID=10001

# 0) Preflight
for bin in docker openssl tr head sed; do
  command -v "$bin" >/dev/null 2>&1 || { echo "[ERROR] missing required tool: $bin" >&2; exit 1; }
done
docker compose version >/dev/null 2>&1 || { echo "[ERROR] docker compose v2 plugin not found" >&2; exit 1; }

# 1) .env from template; stop so the operator reviews it
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "[OK] Created .env from template. Edit the domains and ACME_EMAIL, then run ./setup.sh again."
  exit 0
fi
chmod 600 .env

# 2) Refuse to continue with placeholder values
if grep -Eq '^(SAVI_DOMAIN|CLOUD_DOMAIN|ACME_EMAIL)=.*(example\.(com|org|net)|<[A-Za-z_]+>|CHANGE_ME|changeme)' .env; then
  echo "[ERROR] .env still contains the example domains or email. Edit SAVI_DOMAIN, CLOUD_DOMAIN and ACME_EMAIL." >&2
  exit 1
fi

# 3) Directories and permissions
mkdir -p data/postgres data/caddy/data data/caddy/config data/savi/data data/savi/home secrets backups
chmod 700 secrets backups

# The SAVI container runs as a non-root user: its directories must belong to it.
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$SAVI_UID:$SAVI_GID" data/savi
elif ! chown -R "$SAVI_UID:$SAVI_GID" data/savi 2>/dev/null; then
  echo "[WARN] Could not chown data/savi to $SAVI_UID:$SAVI_GID. Run once:"
  echo "       sudo chown -R $SAVI_UID:$SAVI_GID $(pwd)/data/savi"
fi

# 4) Secrets (only if missing, so a live deployment is never broken)
gen_alnum() {   # usage: gen_alnum LENGTH
  tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1" || [[ ${PIPESTATUS[0]} -eq 141 ]]
}
gen_fernet_key() {   # 32 random bytes, urlsafe base64 (the format Fernet requires)
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
}
write_secret() {   # usage: write_secret NAME GENERATOR [ARG]
  local name="$1"; shift
  if [[ ! -s "secrets/$name.txt" ]]; then
    ( umask 077; "$@" > "secrets/$name.txt" )
    echo "[OK] Generated secrets/$name.txt"
  fi
}
for s in "${AUTO_SECRETS[@]}"; do write_secret "$s" gen_alnum 48; done
for s in "${LONG_SECRETS[@]}"; do write_secret "$s" gen_alnum 64; done
write_secret erp_credentials_key gen_fernet_key

# 5) Manual secrets must exist and must not be empty or placeholders
missing=0
for s in "${MANUAL_SECRETS[@]}"; do
  if [[ ! -s "secrets/$s.txt" ]]; then
    echo "[WARN] secrets/$s.txt is missing or empty (create it with: printf '%s' '<VALUE>' > secrets/$s.txt)"
    missing=1
  elif grep -Eq '^(<.*>|CHANGE_ME|changeme)$' "secrets/$s.txt"; then
    echo "[ERROR] secrets/$s.txt contains a placeholder" >&2
    missing=1
  fi
done
chmod 600 secrets/*.txt 2>/dev/null || true
if [[ $missing -eq 1 ]]; then
  echo "Create the missing secrets and run ./setup.sh again before 'docker compose up -d'." >&2
  exit 1
fi

# 6) Version stamp: the images have no .git, so the version travels as build arguments.
set_env() {   # usage: set_env VAR VALUE (replaces the line; never prints secrets)
  local var="$1" value="$2"
  if grep -q "^${var}=" .env; then
    sed "s|^${var}=.*|${var}=${value}|" .env > .env.tmp && mv .env.tmp .env
  else
    printf '%s=%s\n' "$var" "$value" >> .env
  fi
  chmod 600 .env
}
version="0.0.0-dev"; commit=""
if command -v git >/dev/null 2>&1 && git -C ../.. rev-parse --git-dir >/dev/null 2>&1; then
  version="$(git -C ../.. describe --tags --always --dirty=-sucio --match 'v*' 2>/dev/null || echo 0.0.0-dev)"
  commit="$(git -C ../.. rev-parse --short HEAD 2>/dev/null || true)"
fi
set_env SAVI_VERSION "$version"
set_env SAVI_COMMIT "$commit"
set_env SAVI_BUILT_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[OK] Version: $version"
if [[ "$version" == *-sucio ]]; then
  echo "[WARN] The working tree has uncommitted changes (-sucio). Production should build from a clean tag."
fi

echo
echo "Done. Start with:"
echo "  docker compose up -d --build"
