# SAVI Cloud: API + consola web. El contexto de build es la RAÍZ del monorepo (la consola usa el
# paquete compartido `packages/ui`); ver deploy/master/docker-compose.yml.
# Multi-stage: la consola se compila con Node, el builder resuelve dependencias con uv y la
# imagen final solo lleva el venv, el código y la consola ya compilada, como usuario sin
# privilegios.
ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS console
WORKDIR /console
# npm workspaces: lock único en la raíz; `npm ci` necesita el package.json de cada workspace
# (también el de SAVI, aunque esta imagen no lo compile).
COPY package.json package-lock.json ./
COPY packages/ui/package.json packages/ui/
COPY frontend/package.json frontend/
COPY cloud/frontend/package.json cloud/frontend/
RUN npm ci --no-audit --no-fund
COPY packages/ui/ packages/ui/
COPY cloud/frontend/ cloud/frontend/
RUN npm run build --workspace cloud/frontend


FROM python:${PYTHON_VERSION}-slim AS builder
ARG UV_VERSION=0.12.13
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install "uv==${UV_VERSION}"
WORKDIR /app

# Dependencias primero: esta capa solo se invalida si cambian pyproject.toml o uv.lock.
COPY cloud/backend/pyproject.toml cloud/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY cloud/backend/app ./app
COPY cloud/backend/alembic ./alembic
COPY cloud/backend/alembic.ini cloud/backend/docker-entrypoint.sh ./
RUN uv sync --frozen --no-dev


FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --system --gid 10001 savi \
    && useradd --system --uid 10001 --gid savi --no-create-home --shell /usr/sbin/nologin savi
WORKDIR /app
COPY --from=builder --chown=savi:savi /app /app
COPY --from=console --chown=savi:savi /console/cloud/frontend/dist /app/console
ENV CLOUD_CONSOLE_STATIC_DIR=/app/console
RUN chmod +x /app/docker-entrypoint.sh
USER savi
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
