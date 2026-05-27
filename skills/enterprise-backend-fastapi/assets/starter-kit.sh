#!/usr/bin/env bash
# Bootstrap de backend FastAPI empresarial con uv.

set -e

# 1. Verificar Python 3.12+
python3 --version  # Debe ser >=3.12

# 2. Crear proyecto con uv
uv init --package backend
cd backend

# 3. Dependencias runtime
uv add fastapi 'uvicorn[standard]' sqlalchemy alembic asyncpg \
       pydantic pydantic-settings redis httpx \
       'python-jose[cryptography]' 'passlib[bcrypt]' orjson

# 4. Dependencias dev
uv add --dev pytest pytest-asyncio ruff pyright

# 5. Sync e iniciar
uv sync
uv run uvicorn app.main:app --reload

# 6. Inicializar Alembic
uv run alembic init -t async app/infrastructure/database/migrations
