# SAVI Cloud

Backend de la plataforma SAVI Cloud: vincula instancias de SAVI con un cliente y (en
etapas siguientes) recibe heartbeats y eventos. Diseño en `docs/plataforma/`
(PRD, Fase 2 §7 y Fase 3).

Estado: **E3a (lado Cloud + contrato)**. Vinculación, heartbeat, ingest de eventos y
rotación de credenciales por HTTP (`/api/v1`), CLI de administración y despliegue. El contrato
vive en [`contracts/sync/v1/`](../contracts/sync/v1/README.md). El sincronizador de la
instancia llega en E3b; agregados diarios y particionado, en E4.

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
│   │       ├── instances/    # auth Bearer, heartbeat, rotación, suspender/activar/revocar
│   │       ├── ingest/       # lotes y eventos tipados (idempotentes)
│   │       └── health/       # /health y /ready
│   ├── alembic/              # migraciones (async)
│   ├── tests/
│   └── Dockerfile
(el despliegue vive en ../deploy/master)
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
uv run cloud-admin instance suspend <instance_id>     # ingest responde accepted=0, sin guardar
uv run cloud-admin instance activate <instance_id>    # si estaba por huella, acepta la nueva
uv run cloud-admin instance revoke <instance_id>      # definitivo
```

### API (`/api/v1`)

| Método y ruta | Auth | Notas |
|---|---|---|
| `POST /enrollments/redeem` | token en el cuerpo | 201 · 404 `enrollment_token_invalid` · 403 `client_suspended` · 429 (10 / 15 min por IP) |
| `POST /instances/heartbeat` | Bearer | 60/min por instancia; huella distinta suspende (`fingerprint_mismatch`) |
| `POST /instances/ingest` | Bearer | gzip opcional · máx. 500 eventos y 5 MB descomprimido · 30/min por instancia |
| `POST /instances/credentials/rotate` | Bearer | el secreto anterior vale 24 h |

Errores: `{"errorCode", "message"}`. 401 `instance_unauthorized` / `instance_revoked`; 429
con `Retry-After`. Los límites de tasa son **en memoria** (una réplica); con más réplicas hay
que moverlos a un almacén compartido.

Pendiente para E4: particionado mensual y retención de las tablas `ev_*`,
`ingest_batches` y `heartbeats` (hoy son tablas planas con las PK de idempotencia).

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
  concurrente y lotes concurrentes por HTTP) usa una base **desechable** que crea y borra el propio test. Se activa con:

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
| `CLOUD_CONSOLE_SECRET` | (vacía = consola apagada) | Semilla de la consola: firma de sesiones y cifrado de TOTP. Mínimo 32 caracteres (`openssl rand -hex 32`) |
| `CLOUD_CONSOLE_COOKIE_SECURE` | `true` | La cookie de refresh solo viaja por HTTPS; `false` solo en desarrollo local |
| `CLOUD_LATEST_VERSION` | (vacía) | Última versión publicada de SAVI (p. ej. `v1.3.0`) |
| `CLOUD_LATEST_VERSION_PUBLISHED_AT` | (vacía) | Fecha de publicación (ISO 8601); sin ella no se alerta por instancias desactualizadas |
| `CLOUD_ALERTS_INTERVAL_SECONDS` | `300` | Cada cuánto se evalúan las alertas (`0` = apagado) |

## Consola del staff

API en `/console/api` y autenticación en `/console/auth` (contraseña argon2id + TOTP obligatorio,
refresh en cookie `HttpOnly`). Roles `admin`, `soporte` y `comercial`; la matriz de permisos vive
en `app/modules/staff/domain.py` y cada ruta declara `RequirePermission` (un test recorre el
router y falla si falta alguna).

```powershell
# Primer administrador: imprime una contraseña temporal una sola vez. En el primer ingreso
# tendrá que elegir una contraseña nueva y configurar el TOTP.
uv run cloud-admin staff create --email vos@empresa.com --name "Tu Nombre" --role admin
```

| Módulo | Qué hace |
|---|---|
| `staff` | Usuarios, sesiones, login, MFA y permisos |
| `audit` | Registro de solo inserción de toda acción que modifica estado (trigger en Postgres) |
| `console` | Clientes, instancias, tokens de vinculación, staff y auditoría |
| `metrics` | Definiciones únicas, resumen, uso por cliente, sucursales y usuarios (seudónimos) |
| `alerts` | 10 reglas configurables, motor cada 5 minutos con estado abierta / reconocida / resuelta |

La interfaz web está en [`frontend/`](frontend/README.md) y la sirve el mismo proceso del API
(`CLOUD_CONSOLE_STATIC_DIR`, que la imagen de Docker ya define).

Pendiente: particionado de las tablas de eventos y retención de heartbeats (30 días) y la
tabla agregada `daily_client_metrics` (hoy se calcula al consultar, con el índice
`(client_id, occurred_at)`).

## Despliegue

Ver [`deploy/master/README.md`](../deploy/master/README.md): SAVI, Cloud, PostgreSQL y Caddy
con HTTPS automático en un solo `docker compose`.
