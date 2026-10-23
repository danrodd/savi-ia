#!/usr/bin/env bash
# Prepares the SAVI update server: .env, directories and the publishing user.
# Idempotent: safe to run many times. Never overwrites .env or an authorized key.
#
#   sudo ./setup.sh                          # .env, directories, savi-publish user
#   sudo ./setup.sh --publish-key key.pub    # also authorizes that SSH public key
set -euo pipefail

cd "$(dirname "$0")"

PUBLISH_KEY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --publish-key) PUBLISH_KEY="${2:?--publish-key needs a .pub file}"; shift 2 ;;
    *) echo "[ERROR] unknown argument: $1" >&2; exit 1 ;;
  esac
done

# 0) Preflight
for bin in docker sed grep; do
  command -v "$bin" >/dev/null 2>&1 || { echo "[ERROR] missing required tool: $bin" >&2; exit 1; }
done
docker compose version >/dev/null 2>&1 || { echo "[ERROR] docker compose v2 plugin not found" >&2; exit 1; }

# 1) .env from template; stop so the operator reviews it
if [[ ! -f .env ]]; then
  cp env.template .env
  chmod 600 .env
  echo "[OK] Created .env from env.template. Edit UPDATES_SITE, ACME_EMAIL and the ports, then run ./setup.sh again."
  exit 0
fi
chmod 600 .env

# 2) Refuse to continue with placeholder values
if grep -Eq '^(UPDATES_SITE|ACME_EMAIL)=.*example\.(com|org|net)' .env; then
  echo "[ERROR] .env still contains the example domain or email. Edit UPDATES_SITE and ACME_EMAIL." >&2
  exit 1
fi

env_value() {   # usage: env_value NAME DEFAULT  (last assignment wins, like compose)
  local value
  value="$(sed -n "s/^$1=//p" .env | tail -n 1)"
  echo "${value:-$2}"
}
UPDATES_DIR="$(env_value UPDATES_DIR /srv/savi-updates)"
PUBLISH_USER="$(env_value UPDATES_PUBLISH_USER savi-publish)"
UPDATES_SITE="$(env_value UPDATES_SITE '')"

# 3) Caddy state (certificates must survive restarts)
mkdir -p data/caddy/data data/caddy/config

# 4) Published folder and publishing user (needs root)
if [[ "$(id -u)" -ne 0 ]]; then
  echo "[WARN] Not root: the publishing user and $UPDATES_DIR were not prepared. Run: sudo ./setup.sh"
else
  if ! id "$PUBLISH_USER" >/dev/null 2>&1; then
    # Needs a shell: publish-release.py runs `mkdir` and `mv` over SSH. No sudo, no groups.
    useradd --create-home --shell /bin/bash "$PUBLISH_USER"
    passwd --lock "$PUBLISH_USER" >/dev/null   # SSH key only, never a password
    echo "[OK] Created user $PUBLISH_USER (password login locked)."
  fi

  mkdir -p "$UPDATES_DIR/savi/releases"
  chown root:root "$UPDATES_DIR"
  chmod 755 "$UPDATES_DIR"
  chown -R "$PUBLISH_USER:$PUBLISH_USER" "$UPDATES_DIR/savi"
  # Caddy runs without CAP_DAC_OVERRIDE: everything must be world-readable.
  chmod -R u=rwX,go=rX "$UPDATES_DIR/savi"

  if [[ -n "$PUBLISH_KEY" ]]; then
    [[ -f "$PUBLISH_KEY" ]] || { echo "[ERROR] $PUBLISH_KEY not found" >&2; exit 1; }
    home="$(getent passwd "$PUBLISH_USER" | cut -d: -f6)"
    keys="$home/.ssh/authorized_keys"
    install -d -m 700 -o "$PUBLISH_USER" -g "$PUBLISH_USER" "$home/.ssh"
    touch "$keys"
    key_body="$(awk '{print $2}' "$PUBLISH_KEY")"
    if grep -qF "$key_body" "$keys"; then
      echo "[OK] The key is already authorized for $PUBLISH_USER."
    else
      # `restrict`: no port forwarding, agent, X11 or PTY. Only commands and scp.
      echo "restrict $(cat "$PUBLISH_KEY")" >>"$keys"
      echo "[OK] Authorized the key for $PUBLISH_USER."
    fi
    chown "$PUBLISH_USER:$PUBLISH_USER" "$keys"
    chmod 600 "$keys"
  fi
fi

# 5) Validate the configuration without starting anything
docker compose config --quiet
docker run --rm -e UPDATES_SITE="$UPDATES_SITE" -e ACME_EMAIL="$(env_value ACME_EMAIL '')" \
  -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" "caddy:$(env_value CADDY_VERSION 2.8.4-alpine)" \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
echo "[OK] docker-compose.yml and Caddyfile are valid."

echo
echo "Next:  docker compose up -d"
echo "Publish to:  $PUBLISH_USER@<this-server>:$UPDATES_DIR/savi"
