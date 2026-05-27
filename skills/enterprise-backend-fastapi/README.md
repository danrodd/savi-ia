# enterprise-backend-fastapi

Skill personal/global que encapsula la arquitectura de referencia para backends Python FastAPI empresariales (Clean + Hexagonal + Feature-based). Reemplaza la práctica de pegar `Arquitectura Backend Empresarial Moderna — FastAPI.md` en cada conversación.

## ¿Cuándo se dispara?

Carga automática ante señales como:

- "FastAPI enterprise backend", "Clean Architecture", "Hexagonal"
- `SQLAlchemy 2 async`, `Alembic`, `uv`, Pydantic v2, asyncpg
- Use cases, repositorios, dominio puro, DI con FastAPI
- Estructurar `app/modules/<x>/{domain, application, infrastructure}/`

Si no se dispara sola, invocala con `/enterprise-backend-fastapi`.

## Estructura

```
enterprise-backend-fastapi/
├── SKILL.md                       # Contrato corto — Hard Rules + Decision Gates
├── README.md                      # Este archivo
├── assets/
│   ├── starter-kit.sh             # Bootstrap con uv
│   └── pyproject.toml             # pyproject.toml empresarial de referencia
└── references/
    ├── stack.md                   # FastAPI, uv, SQLAlchemy, Pydantic, Pyright
    ├── principles.md              # Filosofía + dependencias hacia adentro
    ├── module-structure.md        # app/ + anatomía de módulo
    ├── layers-detail.md           # Domain / Application / Infrastructure con ejemplos
    ├── dependency-injection.md    # DI explícita con FastAPI
    ├── testing-and-tooling.md     # Pytest, Ruff, Pyright, uv
    └── errors-and-settings.md     # Mapeo excepciones + Settings tipados
```

## Cómo integrarla en un CLAUDE.md de proyecto

```markdown
## Arquitectura

Este backend sigue la arquitectura empresarial de referencia (Clean + Hexagonal).
Antes de tocar `app/modules/`, `app/shared/` o `app/infrastructure/`, cargá la
skill `enterprise-backend-fastapi` y respetá sus Hard Rules:

- Dependencias hacia adentro: infrastructure → application → domain
- Domain no importa FastAPI/SQLAlchemy/Pydantic
- Use Cases tienen la lógica; controllers son Request→DTO→UseCase→Response
- Repositorios abstraídos como interface en domain/interfaces/
- DTO ≠ ORM ≠ Entity (mappers transforman entre ellos)
- Async-first + Pyright strict + uv como package manager

Ver `~/.claude/skills/enterprise-backend-fastapi/SKILL.md` para el contrato completo.
```

## Actualización

Cuando la nota de Obsidian evolucione:

1. Editá la `references/` correspondiente (Hard Rules cambian en `SKILL.md`).
2. Bumpeá `metadata.version`.
3. Re-corré `/skill-registry` para reindexar.

## Fuente

Basada en `C:\Users\hikig\Documents\Obsidian\hikig\Arquitectura\Arquitectura Backend Empresarial Moderna — FastAPI.md` (snapshot del 2026-05-26).
