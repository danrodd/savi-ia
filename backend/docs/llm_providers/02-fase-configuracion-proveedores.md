# Fase 2 — Configuración de proveedores en la base de datos

> Parte de: [PRD — Proveedores de IA configurables](00-prd.md)
> Estado: **propuesta** · Depende de: [Fase 1](01-fase-tools-neutrales.md) · Habilita: [Fase 3](03-fase-gemini.md)

La configuración de IA sale del `.env` y pasa a la BD del agente,
administrable por API: proveedor activo, modelos, credencial cifrada y
precios. El chat resuelve el proveedor **en cada turno**, así que
cambiarlo no requiere reiniciar. Al terminar la fase solo existe el
proveedor Claude, pero ya configurable en caliente. Las instalaciones
existentes siguen funcionando sin intervención gracias al seed desde el
`.env`.

---

## Resultado esperado

- [ ] Módulo nuevo `app/modules/llm_providers/` (triada Clean completa).
- [ ] Tabla `llm_provider_configs` con migración Alembic, verificada en Postgres y SQLite.
- [ ] Credenciales cifradas con Fernet; nunca salen del backend.
- [ ] Seed idempotente desde `CLAUDE_*` / `ANTHROPIC_API_KEY` del `.env`.
- [ ] API de administración `/admin/llm-providers`.
- [ ] `LLMRunnerFactory` y `TitleGeneratorFactory` resuelven el proveedor activo por turno, con cache e invalidación.
- [ ] Cambiar la credencial o el modelo de Claude aplica al siguiente turno, sin reiniciar.

## Fuera de alcance

- Implementación de Gemini (solo se declara en el catálogo) → [Fase 3](03-fase-gemini.md).
- Pantalla de administración → [Fase 4](04-fase-interfaz-admin-y-e2e.md).
- Incluir proveedores en el export/import entre agentes (PRD, P2).

---

## 1. Catálogo de proveedores soportados

Un descriptor en código por proveedor. Es lo que la UI usa para saber
qué campos pedir, y lo que la factory usa para saber qué adaptador
construir.

`llm_providers/domain/value_objects/provider_kind.py`:

```python
class ProviderKind(StrEnum):
    CLAUDE = "claude"
    GEMINI = "gemini"


class CredentialKind(StrEnum):
    API_KEY = "api_key"          # Claude y Gemini
    OAUTH_TOKEN = "oauth_token"  # solo Claude (CLAUDE_CODE_OAUTH_TOKEN)
    LOCAL_SESSION = "local_session"  # solo Claude: `claude login` del equipo
```

`llm_providers/domain/entities/provider_descriptor.py` (estático, no persiste):

| Campo | Claude | Gemini |
|---|---|---|
| `kind` | `claude` | `gemini` |
| `display_name` | Claude (Anthropic) | Gemini (Google) |
| `credential_kinds` | `api_key`, `oauth_token`, `local_session` | `api_key` |
| `supports_model_listing` | No: se ingresan a mano | Sí (`client.aio.models.list`) |
| `implemented` | Sí | Sí a partir de la Fase 3 |

Agregar un proveedor = agregar un descriptor + su adaptador. La UI y la API
no cambian.

## 2. Modelo de datos

### Tabla `llm_provider_configs` (BD del agente)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `provider` | `String(32)` NOT NULL | `ProviderKind`. **Único**: una fila por proveedor. |
| `credential_kind` | `String(32)` NOT NULL | `CredentialKind`; validado contra el descriptor. |
| `credential_encrypted` | `Text` NULL | Token Fernet. `NULL` si `local_session`. |
| `credentials_unreadable` | `Boolean` NOT NULL default false | Si el descifrado falla (cambió la clave). Mismo patrón que `erp_databases`. |
| `chat_model` | `String(120)` NOT NULL | ID del modelo de chat. |
| `title_model` | `String(120)` NOT NULL | ID del modelo de títulos. |
| `pricing` | JSON NOT NULL default `{}` | `{ "<model_id>": { "input": n, "output": n, "cache_read": n, "cache_write": n } }` en USD por millón de tokens. |
| `is_active` | `Boolean` NOT NULL default false | Índice único parcial `WHERE is_active`: solo un activo. |
| `last_test_ok_at` | `UtcDateTime` NULL | Última prueba de credencial exitosa. |
| `created_at` / `updated_at` | `UtcDateTime` NOT NULL | |

Decisiones:

- **Una fila por proveedor, no por "configuración".** Alcanza con un activo
  global (PRD, no objetivos), y evita elegir entre configuraciones
  duplicadas del mismo proveedor.
- **Sin borrado.** Desactivar = activar otro. Una fila sin usar no molesta
  y conserva su key para volver atrás rápido.
- **El índice parcial se verifica en los dos caminos de SQLite** (`create_all`
  + `stamp` y `upgrade`), extendiendo `test_ensure_schema_migration_paths.py`.
- Registrar el modelo nuevo en `bootstrap.py::_REGISTERED_MODELS` y en
  `alembic/env.py`.

### Cifrado compartido

Hoy `CredentialCipher` y `FernetCredentialCipher` viven en
`erp_databases`, y `auth` ya los importa desde ahí. Con un tercer
consumidor pasan a código compartido:

```
app/shared/security/
├── credential_cipher.py         # puerto (antes erp_databases/domain/interfaces)
└── fernet_credential_cipher.py  # impl (antes erp_databases/infrastructure/security)
```

- Se reutiliza **la misma clave** `ERP_CREDENTIALS_KEY` (y
  `ERP_CREDENTIALS_KEY_OLD` para rotación). No se renombra la variable: el
  instalador la genera y renombrarla rompería las instalaciones
  existentes. Se documenta que ahora protege también las keys de IA.
- `erp_databases` y `auth` pasan a importar desde `app/shared/security`.
  El cambio es mecánico y no altera comportamiento.

## 3. Capa de aplicación

`llm_providers/application/use_cases/manage_llm_providers.py`:

| Método | Regla |
|---|---|
| `list()` | Devuelve **todos** los descriptores, con su config si existe. Nunca incluye la credencial: solo `has_credential: bool`. |
| `save(provider, dto)` | Crea o actualiza la fila. Credencial vacía = conservar la guardada (mismo contrato que las bases del ERP). Valida `credential_kind` contra el descriptor. Invalida la cache. |
| `test(provider, dto)` | Prueba la credencial **sin persistir** (con la guardada si viene vacía). Devuelve `ok`, `detail` y `models` si el proveedor lista modelos. |
| `list_models(provider)` | Modelos disponibles con la credencial guardada. |
| `activate(provider)` | Exige que haya config, credencial legible (salvo `local_session`), `chat_model` y `title_model`. Baja el activo anterior y sube el nuevo en la misma transacción. Invalida la cache. |

**Puerto de prueba de credencial** — `llm_providers/domain/interfaces/provider_probe.py`:

```python
class ProviderProbe(ABC):
    @abstractmethod
    async def test(self, config: LlmProviderConfig) -> ProbeResult: ...
```

- `ClaudeProbe`: corre un turno mínimo del SDK con `max_turns=1`, sin
  tools, con el modelo de títulos. No hay endpoint para listar modelos, así
  que `models` queda vacío y la UI pide el ID a mano.
- `GeminiProbe` llega en la Fase 3.
- El probe **nunca levanta**: una key inválida es `ok=False` con un detalle
  accionable, igual que `ConnectionTester` para las bases del ERP.

## 4. Seed desde el `.env`

`llm_providers/infrastructure/seed.py`. Corre en el `lifespan`, después de
`ensure_schema`:

```
si la tabla está vacía:
    credential_kind =
        oauth_token    si CLAUDE_CODE_OAUTH_TOKEN tiene valor
        api_key        si no, y ANTHROPIC_API_KEY tiene valor
        local_session  si ninguna
    insertar fila claude con CLAUDE_MODEL / CLAUDE_TITLE_MODEL, is_active=true
```

- Idempotente por "tabla vacía", como el seed de `erp_databases`: si el
  administrador reconfiguró desde la UI, reiniciar no pisa nada.
- Las variables `CLAUDE_*` siguen en `Settings` con sus defaults: solo se
  leen para sembrar. `env.template` del instalador no cambia.
- Sin credencial en el `.env` la fila queda como `local_session`, que es
  exactamente el comportamiento actual del CLI (`claude login`).

## 5. Resolución del proveedor por turno

### Puerto en el chat

`chat/domain/interfaces/active_provider.py`:

```python
@dataclass(frozen=True, slots=True)
class ActiveProvider:
    kind: str
    chat_model: str
    title_model: str
    credential_kind: str
    credential: str | None      # en claro, solo en memoria del proceso
    pricing: dict[str, ModelPricing]


class ActiveProviderResolver(ABC):
    @abstractmethod
    async def resolve(self) -> ActiveProvider: ...
```

El chat no importa `llm_providers`: depende de este puerto, y la
implementación vive en `llm_providers/infrastructure/active_provider_resolver.py`.

### Cache

- En memoria del proceso, **sin TTL**. Se invalida explícitamente en
  `save` y `activate`: la única forma de cambiar la config es por este
  módulo, así que no hace falta expirar por tiempo (RNF-06).
- Sin proveedor activo o con credencial ilegible, `resolve()` levanta
  `NoActiveProviderError`. `routes.py` la convierte en **409** con
  `errorCode: "llm_provider_unavailable"` **antes** de abrir el SSE, igual
  que `erp_database_unavailable`.

### Factories

`chat/infrastructure/llm/factory.py`:

```python
class LLMRunnerFactory:
    def build(self, provider: ActiveProvider) -> LLMRunner: ...

class TitleGeneratorFactory:
    def build(self, provider: ActiveProvider) -> TitleGenerator: ...
```

- `dependencies.py` deja de construir `ClaudeAgentRunner` fijo: resuelve el
  proveedor y le pide el runner a la factory.
- **Auto-título:** el `ConversationTitleUpdater` resuelve el proveedor al
  momento de generar, no al inicio del turno. Si el administrador cambió de
  proveedor a mitad del stream, el título usa el nuevo.

### Credencial de Claude por turno (riesgo R5 del PRD)

Hoy `_apply_sdk_env` hace `os.environ.setdefault(...)` una vez por proceso.
Con `setdefault`, cambiar la key desde la UI **no tendría efecto** hasta
reiniciar.

- **Verificado (2026-09-13):** `ClaudeAgentOptions` de `claude-agent-sdk`
  0.2.87 tiene el campo `env`.
- El runner y el generador de títulos pasan la credencial en
  `ClaudeAgentOptions(env={...})` en cada consulta y se elimina
  `_apply_sdk_env`.
- Con `local_session` no se inyecta ninguna variable: el CLI usa su propio
  login. Es el comportamiento actual.
- `CLAUDE_CODE_GIT_BASH_PATH` sigue viniendo de `Settings`: es
  infraestructura del equipo, no configuración del proveedor.

## 6. API de administración

Prefijo `/admin/llm-providers`, todos con `SaviAdminDep` (`admin` ya está en `_API_PREFIXES`).

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| `GET` | `""` | — | `LlmProviderResponse[]`: un item por proveedor soportado |
| `PUT` | `/{provider}` | `SaveLlmProviderRequest` | `LlmProviderResponse` |
| `POST` | `/{provider}/test` | `SaveLlmProviderRequest` | `ProviderTestResponse` |
| `GET` | `/{provider}/models` | — | `{ models: ModelInfo[] }` |
| `POST` | `/{provider}/activate` | — | `LlmProviderResponse` |

```ts
// LlmProviderResponse — nunca incluye la credencial
{
  provider: "claude" | "gemini";
  display_name: string;
  implemented: boolean;
  credential_kinds: string[];
  supports_model_listing: boolean;
  configured: boolean;
  credential_kind: string | null;
  has_credential: boolean;
  credentials_unreadable: boolean;
  chat_model: string | null;
  title_model: string | null;
  pricing: Record<string, { input: number; output: number; cache_read: number; cache_write: number }>;
  is_active: boolean;
  last_test_ok_at: string | null;
}

// SaveLlmProviderRequest
{
  credential_kind: string;
  credential?: string;       // vacío = conservar la guardada
  chat_model: string;
  title_model: string;
  pricing?: Record<string, {...}>;
}

// ProviderTestResponse
{ ok: boolean; detail: string; models: { id: string; display_name: string }[] }
```

Errores:

| Caso | Status |
|---|---|
| Proveedor desconocido | 404 |
| Proveedor no implementado (antes de la Fase 3, `gemini`) | 422 |
| `credential_kind` no soportado por el proveedor | 422 |
| Activar sin credencial legible o sin modelos | 422 |

---

## Estructura del módulo

```
app/modules/llm_providers/
├── domain/
│   ├── entities/          # LlmProviderConfig, ProviderDescriptor
│   ├── value_objects/     # ProviderKind, CredentialKind, ModelPricing
│   ├── interfaces/        # LlmProviderRepository, ProviderProbe
│   └── exceptions/        # ProviderNotFound, ProviderNotImplemented, NoActiveProvider
├── application/
│   ├── dtos/ requests/ responses/
│   └── use_cases/manage_llm_providers.py
└── infrastructure/
    ├── persistence/       # modelo ORM + repositorio (frontera del cifrado)
    ├── probes/claude_probe.py
    ├── active_provider_resolver.py
    ├── seed.py
    └── http/              # routes + dependencies
```

## Tests

| Test | Verifica |
|---|---|
| `test_llm_provider_repository.py` | Credencial cifrada en BD (no en claro); ida y vuelta; clave equivocada → `credentials_unreadable`, sin excepción. |
| `test_single_active_provider.py` | El índice parcial impide dos activos; `activate` baja el anterior. |
| `test_manage_llm_providers.py` | Credencial vacía conserva la guardada; activar sin modelos o sin credencial da 422; proveedor no implementado da 422. |
| `test_llm_provider_seed.py` | Los tres casos de `credential_kind` desde el `.env`; idempotencia; no pisa una tabla con datos. |
| `test_active_provider_cache.py` | Una sola lectura a BD por varias resoluciones; `save` y `activate` invalidan. |
| `test_no_credential_leak.py` | Ningún response de `/admin/llm-providers` contiene la credencial, ni en claro ni cifrada. |
| `test_chat_409_without_provider.py` | `POST /chat` sin proveedor activo → 409 `llm_provider_unavailable` antes del SSE. |
| `test_ensure_schema_migration_paths.py` (extendido) | La tabla y su índice parcial en ambos caminos de SQLite. |

## Verificación

- [ ] Lint, typecheck y suite completa en verde.
- [ ] Migración aplicada sobre la BD de desarrollo (Postgres).
- [ ] Arranque en una BD con datos previos: el seed deja Claude activo y el chat responde igual que antes.
- [ ] Por API: cambiar `chat_model` de Claude → el siguiente turno usa el modelo nuevo, sin reiniciar (visible en el log del SDK).
- [ ] Por API: reemplazar la credencial → aplica al siguiente turno.
- [ ] `grep` sin `CLAUDE_MODEL` ni `ANTHROPIC_API_KEY` leídos fuera de `seed.py`.
