---
name: enterprise-backend-fastapi
description: "Trigger: FastAPI enterprise backend, Clean/Hexagonal architecture, use cases, repositories, SQLAlchemy 2 async, Pydantic v2, uv. Aplica arquitectura backend de referencia."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Carga esta skill cuando se vaya a:

- Crear o auditar un backend Python FastAPI empresarial (Clean + Hexagonal + Feature-based).
- Estructurar `app/modules/<dominio>/{domain, application, infrastructure}/`.
- Crear use cases, entities, repositorios (interfaces en domain, implementación en infrastructure).
- Configurar SQLAlchemy 2 async + Alembic + asyncpg + PostgreSQL.
- Definir Requests/DTOs/Responses/Entities con separación estricta.
- Configurar DI con FastAPI dependencies, Pydantic v2 settings, middleware compartido.
- Setup de uv, Ruff, Pyright (strict), Pytest (unit / integration / e2e).

NO la cargues para: fixes triviales, scripts one-off, proyectos no-FastAPI, prototipos sin requerimientos de mantenibilidad.

## Hard Rules

- **Dependencias hacia adentro**: `infrastructure → application → domain`. NUNCA al revés.
- **Domain puro**: NO importa FastAPI, SQLAlchemy, Pydantic, Redis, HTTP. Sólo entities, interfaces, value objects, exceptions, reglas de negocio.
- **Use Cases tienen la lógica**: NUNCA mover lógica al controller. Controllers son `Request → DTO → UseCase → Response` y nada más.
- **Repositorios abstraídos**: `application` depende de **interfaces** (`UserRepository` en `domain/interfaces/`), no de SQLAlchemy.
- **DTO ≠ ORM ≠ Entity**: nunca retornar modelos SQLAlchemy directamente. Mappers convierten ORM ↔ Entity ↔ DTO.
- **Requests/Responses** usan Pydantic v2. **DTOs internos** usan `@dataclass` (no Pydantic — son transporte interno).
- **Async-first**: todo I/O es `async`. `asyncpg` + `SQLAlchemy 2 async`.
- **Tipado estricto**: Pyright en `strict` mode. Sin `Any` salvo justificación documentada.
- **Settings tipados**: `BaseSettings` de pydantic-settings, validados al arranque desde `.env`. La app falla temprano si falta config crítica.
- **Errores mapeados centralmente**: en `shared/exceptions/` (DomainError→400, ValidationError→422, Unauthorized→401, Forbidden→403).
- **uv** es el package manager. NO `pip`, `poetry`, `pipenv`, `conda`.

## Decision Gates

| Decisión | Acción |
|----------|--------|
| ¿Nuevo dominio? | Crear `app/modules/<x>/` con la triada `domain/`, `application/`, `infrastructure/` — ver [references/module-structure.md](references/module-structure.md) |
| ¿Nueva acción de negocio? | Crear un Use Case (`{Verbo}{Recurso}UseCase`) en `application/use_cases/` |
| ¿Acceso a DB/Redis/API externa? | Implementación en `infrastructure/`. Si lo necesita el dominio → definí interface en `domain/interfaces/` y inyectá la impl |
| ¿Validación de input HTTP? | Pydantic Request en `application/requests/` |
| ¿Validación de regla de negocio? | Value Object o Validator en `domain/` o `application/validators/` |
| ¿Settings nuevos? | Agregar a `infrastructure/config/settings.py` (`BaseSettings`) + `.env.example` |
| ¿Excepción nueva? | Excepción de dominio en `domain/exceptions/` + mapeo HTTP en `shared/exceptions/` |
| ¿Test de use case? | `tests/unit/` con mocks de repos. Sin DB real |
| ¿Test de repo? | `tests/integration/` contra PostgreSQL real |
| ¿Test de endpoint completo? | `tests/e2e/` con httpx + lifecycle de app |

## Execution Steps

1. Antes de tocar código, leé la reference relevante según el gate (módulo, capas, testing, DI).
2. En proyecto nuevo: ejecutá [assets/starter-kit.sh](assets/starter-kit.sh) y validá `requires-python = ">=3.12"` en `pyproject.toml`.
3. Para cada cambio, verificá las Hard Rules. Si rompés una, justificalo en el PR.
4. Corré `uv run ruff check . && uv run pyright && uv run pytest` antes de cerrar trabajo.

## Output Contract

Cuando apliques esta skill, entregá:

- Cambios alineados con la triada `domain/application/infrastructure` del módulo.
- Use cases sin acoplamiento a FastAPI ni SQLAlchemy.
- Repositorios definidos como interface en `domain/interfaces/` e implementados en `infrastructure/persistence/repositories/`.
- Controllers que sólo orquestan `Request → DTO → UseCase → Response`.
- Tests separados por tipo (unit/integration/e2e) según lo que pruebas.
- Si introducís una dependencia nueva, justificá por qué no alcanzaba el stack base.

## References

- [references/stack.md](references/stack.md) — Stack base, versiones, herramientas.
- [references/principles.md](references/principles.md) — Filosofía y principios arquitectónicos.
- [references/module-structure.md](references/module-structure.md) — Estructura `app/`, anatomía de módulo, capas.
- [references/layers-detail.md](references/layers-detail.md) — Domain, Application, Infrastructure en detalle con ejemplos.
- [references/dependency-injection.md](references/dependency-injection.md) — DI explícita con FastAPI.
- [references/testing-and-tooling.md](references/testing-and-tooling.md) — Pytest, Ruff, Pyright, uv.
- [references/errors-and-settings.md](references/errors-and-settings.md) — Mapeo de excepciones y Settings tipados.
- [assets/starter-kit.sh](assets/starter-kit.sh) — Bootstrap con uv.
- [assets/pyproject.toml](assets/pyproject.toml) — pyproject.toml empresarial de referencia.
