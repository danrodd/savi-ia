# Stack Base

| Capa | Tecnología | Función |
|------|------------|---------|
| Framework | FastAPI | API HTTP async |
| Runtime | Python 3.12+ | Lenguaje principal |
| Package Manager | uv | Dependencias y entornos |
| ORM | SQLAlchemy 2.x Async | Persistencia |
| Migraciones | Alembic | Versionamiento DB |
| Validación | Pydantic v2 | Requests/Responses + Settings |
| DB Driver | asyncpg | PostgreSQL async |
| Linter / Format | Ruff | Lint + format unificado |
| Type Checker | Pyright | Tipado estricto (`strict` mode) |
| Testing | Pytest + pytest-asyncio | Tests unit/integration/e2e |
| ASGI Server | Uvicorn | Producción + dev |

## Reglas no negociables

- `requires-python = ">=3.12"` en `pyproject.toml`.
- `uv` es el ÚNICO package manager. No mezclar con `pip`, `poetry`, `pipenv`.
- `pyright` en `strict` mode (`typeCheckingMode = "strict"` en `pyproject.toml`).
- `ruff` reemplaza a black + isort + flake8.
- I/O siempre `async`. Sin código sync para acceso a DB / HTTP externo.
