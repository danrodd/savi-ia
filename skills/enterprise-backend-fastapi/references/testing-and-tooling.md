# Testing, Linting y Tooling

## Testing

```
tests/
├── unit/           # use cases, validators, services con mocks
├── integration/    # repositorios contra PostgreSQL real, Redis real
└── e2e/            # endpoints completos con httpx + lifecycle
```

### Unit

- Prueban: use cases, validators, services.
- **Sin DB real**. Repos mockeados con implementaciones in-memory que cumplen la interface del dominio.
- Rápidos (<1s por test).

### Integration

- Prueban: repositorios SQLAlchemy contra PostgreSQL real (Docker o testcontainers), clientes Redis, APIs externas.
- Cada test arranca con DB limpia (fixture).

### E2E

- Prueban: endpoints completos vía `httpx.AsyncClient` con `lifespan` de la app real.
- Validan autenticación, autorización, flujos completos.

## Linting y Tooling

| Tool | Comando | Función |
|------|---------|---------|
| Ruff | `uv run ruff check .` | Lint |
| Ruff | `uv run ruff format .` | Format (reemplaza black + isort) |
| Pyright | `uv run pyright` | Type-check estricto |
| Pytest | `uv run pytest` | Tests |

### Configuración base

```toml
# pyproject.toml
[tool.ruff]
line-length = 100

[tool.pyright]
typeCheckingMode = "strict"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["app/tests"]
```

## Workflow estándar

```bash
uv sync                                    # instalar deps
uv run uvicorn app.main:app --reload       # dev server
uv run ruff check . && uv run ruff format . && uv run pyright && uv run pytest
```

Si cualquier paso falla, el cambio NO se mergea.
