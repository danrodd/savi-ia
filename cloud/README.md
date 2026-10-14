# SAVI Cloud

Backend de la plataforma SAVI Cloud: vincula instancias de SAVI con un cliente y (en
etapas siguientes) recibe heartbeats y eventos. Diseño en `docs/plataforma/`
(PRD, Fase 2 §7 y Fase 3).

Estado: **esqueleto desplegable (E2)**. Modelo de datos, lógica de vinculación, CLI de
administración y despliegue. Los endpoints `redeem`/`heartbeat`/`ingest` llegan en E3.

## Estructura

```
cloud/
├── backend/                  # proyecto uv `savi-cloud` (Python 3.12)
│   ├── app/
│   │   ├── main.py           # create_app(): CORS cerrado, cabeceras de seguridad, logs JSON
│   │   ├── config.py         # Settings (variables CLOUD_*)
│   │   ├── db.py             # Base, engine y sessionmaker async
│   │   ├── models.py         # registra los modelos para Alembic
│   │   ├── cli.py            # `cloud-admin`
│   │   ├── shared/           # errores de dominio, reloj, generación/hash de tokens
│   │   └── modules/
│   │       ├── clients/      # domain.py · application.py · infrastructure.py
│   │       ├── enrollments/  # tokens de vinculación (crear, revocar, listar, canjear)
│   │       ├── instances/    # modelo y listado (el resto llega en E3)
│   │       └── health/       # /health y /ready
│   ├── alembic/              # migraciones (async)
│   ├── tests/
│   └── Dockerfile
└── deploy/                   # docker-compose, Caddyfile, backup, README en español
```

Capas por módulo: `domain` (entidades, errores, puertos) ← `application` (casos de uso) ←
`infrastructure` (SQLAlchemy). Los casos de uso no abren transacciones: lo hace el llamador
(CLI hoy, endpoint HTTP en E3).

## Desarrollo local

```bash
cd cloud/backend
uv sync

export CLOUD_DATABASE_URL="postgresql+asyncpg://USUARIO:CLAVE@localhost:5432/savi_cloud_dev"
uv run alembic upgrade head
uv run python -m uvicorn app.main:create_app --factory --port 8800
curl localhost:8800/health ; curl localhost:8800/ready
```

Con `CLOUD_ENV=development` se habilitan `/docs` y `/openapi.json`.

### CLI de administración

```bash
uv run cloud-admin client create --code FARMX --name "Farmacias X"
uv run cloud-admin client list
uv run cloud-admin token create --client FARMX --expires-hours 72   # imprime el token una vez
uv run cloud-admin token list --client FARMX
uv run cloud-admin token revoke <token_id>
uv run cloud-admin instance list --client FARMX
```

`token create` escribe el token solo en stdout (y los metadatos en stderr), para poder
capturarlo en un script.

### Calidad y tests

```bash
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -q
```

- La mayoría de los tests corren sobre SQLite (sin servidor) y repositorios en memoria.
- `tests/test_postgres.py` (migraciones arriba/abajo, deriva de esquema, `/ready`, canje
  concurrente) usa una base **desechable** que crea y borra el propio test. Se activa con:

  ```bash
  export CLOUD_TEST_PG_PASSWORD=...        # obligatoria; sin ella los tests se saltan
  # opcionales: CLOUD_TEST_PG_HOST (localhost), CLOUD_TEST_PG_PORT (5432), CLOUD_TEST_PG_USER (postgres)
  ```

  Las credenciales nunca se guardan en el repositorio.

### Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `CLOUD_DATABASE_URL` | (obligatoria) | `postgresql+asyncpg://...` |
| `CLOUD_ENV` | `production` | `development` habilita `/docs` |
| `CLOUD_LOG_LEVEL` | `INFO` | Nivel de logs JSON |
| `CLOUD_CORS_ORIGINS` | `[]` | JSON con orígenes permitidos (cerrado por defecto) |
| `CLOUD_ENROLLMENT_TOKEN_TTL_HOURS` | `72` | Vigencia por defecto de un token |

## Despliegue

Ver [`deploy/README.md`](deploy/README.md).
