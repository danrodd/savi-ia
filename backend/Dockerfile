# SAVI (backend + frontend) para servidor Linux.
#
# El contexto de build es la RAÍZ del monorepo (necesita `frontend/` y `backend/`):
#   docker build -f backend/Dockerfile -t savi:local .
# En el despliegue lo construye `deploy/master/docker-compose.yml`.
#
# Multi-stage: el frontend se compila con Node, las dependencias se resuelven con uv y la
# imagen final solo lleva el venv, el código, la SPA y el modelo de embeddings, como usuario
# sin privilegios. Ningún secreto entra a una capa: se montan en runtime (`*_FILE`).
ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=22


# ── 1. Frontend ──────────────────────────────────────────────────────
FROM node:${NODE_VERSION}-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG APP_VERSION=0.0.0-dev
# Base relativa: el backend sirve la SPA desde su mismo origen, así que las llamadas al API
# no llevan host. La landing comercial es del sitio público, no de la aplicación.
ENV VITE_API_BASE_URL=/ \
    VITE_LANDING_ENABLED=false \
    VITE_APP_VERSION=${APP_VERSION}
RUN npm run build


# ── 2. Dependencias de Python y modelo de embeddings ─────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ARG UV_VERSION=0.12.13
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install "uv==${UV_VERSION}"
WORKDIR /app

# Dependencias primero: esta capa solo se invalida si cambian pyproject.toml o uv.lock.
# `--no-install-project`: el código corre desde /app (así `resource_dir()` resuelve igual que
# en desarrollo: alembic, catálogo de conocimiento, SPA y modelos cuelgan de esa raíz).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# El modelo de búsqueda viaja en la imagen: sin esto cada arranque en frío bajaría 118 MB y el
# servidor dependería de Hugging Face para responder. Va a `/app/.models`, que es donde lo busca
# `resolve_model_dir` fuera del instalador.
# La configuración de runtime no existe en el build: se usa una mínima solo para esta orden.
RUN AGENT_DB_ENGINE=sqlite APP_ENV=development /app/.venv/bin/python -c \
    "from app.cli import download_embedding_model; download_embedding_model()"

# Sello de versión: en la imagen no hay `.git`, así que viaja incrustada (como en el instalador).
ARG APP_VERSION=0.0.0-dev
ARG APP_COMMIT=""
ARG APP_BUILT_AT=""
RUN printf 'VERSION = "%s"\nCOMMIT = "%s"\nBUILT_AT = "%s"\n' \
    "${APP_VERSION}" "${APP_COMMIT}" "${APP_BUILT_AT}" > app/_build_version.py


# ── 3. Imagen final ──────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/home/savi \
    XDG_DATA_HOME=/data

# `ca-certificates`: las llamadas a los proveedores de IA y a las bases del ERP por TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 savi \
    && useradd --system --uid 10001 --gid savi --create-home --home-dir /home/savi \
        --shell /usr/sbin/nologin savi \
    && mkdir -p /data \
    && chown savi:savi /data

WORKDIR /app
COPY --from=builder --chown=savi:savi /app /app
COPY --from=frontend --chown=savi:savi /build/dist /app/frontend
COPY --chown=savi:savi backend/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# El CLI de Claude se niega a correr con `bypassPermissions` como root: este usuario es
# requisito funcional, no solo higiene.
USER savi
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
