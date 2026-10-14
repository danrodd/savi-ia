# SAVI Cloud API. Multi-stage: el builder resuelve dependencias con uv; la imagen final
# solo lleva el venv y el código, y corre como usuario sin privilegios.
ARG PYTHON_VERSION=3.12

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
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini docker-entrypoint.sh ./
RUN uv sync --frozen --no-dev


FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --system --gid 10001 savi \
    && useradd --system --uid 10001 --gid savi --no-create-home --shell /usr/sbin/nologin savi
WORKDIR /app
COPY --from=builder --chown=savi:savi /app /app
RUN chmod +x /app/docker-entrypoint.sh
USER savi
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
