# Fase 0 — Cierre urgente

> Objetivo: que el chat deje de poder ejecutar código y leer archivos de la
> máquina, y que no haya secretos por defecto ni dependencias con CVE conocidas.
> Esfuerzo estimado: **1 día**. Sin decisiones de producto pendientes.

## Alcance

| # | Hallazgo | Severidad |
|---|---|---|
| C1 | El agente de Claude tiene 31 herramientas integradas con `bypassPermissions` | Crítica |
| M2 | Se acepta el `JWT_SECRET` por defecto | Media |
| M3 | `starlette`, `python-multipart`, `cryptography` y `pydantic-settings` con CVE | Media |
| O3 | `/health` público ejecuta una consulta contra la BD | Media |

---

## C1 — Restringir las herramientas del agente

### Qué está mal

`ClaudeAgentOptions` recibe `allowed_tools` (aprobar sin preguntar) pero no
`tools` (qué herramientas existen). Sin `tools`, el CLI carga su set completo:
`Bash`, `Read`, `Write`, `Edit`, `WebFetch`, `WebSearch`, `Task` y 24 más, y
`permission_mode="bypassPermissions"` las aprueba todas.

### Cambios

**`backend/app/modules/chat/infrastructure/llm/claude/runner.py`** (`_build_options`, ~línea 89):

```python
return ClaudeAgentOptions(
    model=provider.chat_model,
    system_prompt=SYSTEM_PROMPT,
    mcp_servers={MCP_SERVER_NAME: build_mcp_server(tools)},
    # `tools=[]` apaga TODAS las herramientas integradas del CLI (Bash, Read,
    # Write, WebFetch…). `allowed_tools` solo evita el prompt de permiso: no
    # restringe qué existe. Sin esto, `bypassPermissions` deja al chat
    # ejecutar comandos y leer el .env de la máquina donde corre SAVI.
    tools=[],
    allowed_tools=allowed_tool_names(tools),
    disallowed_tools=_BUILTIN_TOOLS,   # segunda barrera, por si cambia el default del CLI
    permission_mode="bypassPermissions",
    ...
)
```

`_BUILTIN_TOOLS` es una constante del módulo con los nombres observados en el
mensaje `init` del CLI.

**`backend/app/modules/chat/infrastructure/llm/claude/title_generator.py`** (~línea 27):
agregar `tools=[]` junto al `allowed_tools=[]` que ya está.

### Criterios de aceptación

- [ ] `_build_options(...)` devuelve `tools == []` y `disallowed_tools` no vacío.
- [ ] Las opciones del generador de títulos también traen `tools=[]`.
- [ ] En una corrida real, el mensaje `init` del CLI lista **solo** las herramientas `mcp__savi__*` y ninguna integrada.
- [ ] El chat sigue respondiendo con datos del ERP y citando documentos (E2E existente en verde).

### Tests

| Test | Dónde | Qué verifica |
|---|---|---|
| `test_claude_options_disable_builtin_tools` | `backend/tests/unit/modules/chat/` | `_build_options` fija `tools=[]` y las 4 tools MCP en `allowed_tools`. |
| `test_title_options_disable_builtin_tools` | ídem | El generador de títulos no habilita herramientas. |
| E2E `company-knowledge.spec.ts` | `frontend/e2e/` | Ya existe: respuesta con 7,5 citando la fuente. Debe seguir en verde. |

### Verificación manual

1. Correr el sondeo que se usó en la revisión: imprime las herramientas del `init`. Esperado: solo `mcp__savi__…`.
2. Hacer 3 preguntas reales por el chat y comparar `usage` contra la medición previa (**~144.000 tokens de contexto por respuesta**). Esperado: una caída fuerte.
3. Anotar el número nuevo en `docs/revision-general.md`.

### Efecto esperado más allá de la seguridad

- Menos tokens por respuesta y, por lo tanto, menos costo.
- Si el contexto baja lo suficiente, **revisar si sigue haciendo falta la regla de "máximo 4 tools MCP"** de `CLAUDE.md`: el modo *deferred tools* probablemente lo disparaban las 31 integradas, no las 4 propias. Si se confirma, actualizar `CLAUDE.md` y `backend/docs/mcp_deferred_tools_gotcha.md` con la causa real.

---

## M2 — No arrancar con el secreto por defecto

### Qué está mal

`jwt_secret` tiene default `"change-me-in-prod"`. Si el `.env` no lo define,
SAVI arranca igual y cualquiera que conozca el default puede firmarse un token
de administrador.

### Cambios

**`backend/app/infrastructure/config/settings.py`**: agregar un `model_validator`
junto al que ya valida las credenciales de Postgres.

```python
_INSECURE_JWT_SECRET = "change-me-in-prod"

@model_validator(mode="after")
def _reject_default_jwt_secret(self) -> "Settings":
    """Fuera de desarrollo, el secreto por defecto es una puerta abierta:
    firma tokens de administrador válidos para cualquiera que lo conozca."""
    if self.app_env != "development" and self.jwt_secret.strip() == _INSECURE_JWT_SECRET:
        raise ValueError(
            "JWT_SECRET tiene el valor por defecto. Generá uno nuevo antes de "
            "usar SAVI fuera de desarrollo."
        )
    return self
```

Además, loguear un `warning` claro al arrancar en `development` con el default.

### Criterios de aceptación

- [ ] Con `APP_ENV=production` y el secreto por defecto, la app **no arranca** y el mensaje dice qué hacer.
- [ ] Con `APP_ENV=development`, arranca pero deja un warning en el log.
- [ ] El instalador sigue funcionando (ya genera el secreto; verificar el camino de fallo de `savi.iss:1018`).

### Tests

- `test_settings_reject_default_jwt_secret_outside_development`.
- `test_settings_allow_default_jwt_secret_in_development`.

---

## M3 — Actualizar dependencias con CVE

### Qué está mal

| Paquete | Actual | Mínimo | Por qué importa |
|---|---|---|---|
| `starlette` | 1.1.0 | 1.3.1 | Límites de `request.form()` no aplicados y `request.url` mal reconstruida. SAVI recibe formularios multipart. |
| `python-multipart` | 0.0.29 | 0.0.31 | `Content-Length` negativo y parsing de `;` como separador. Mismo camino: subida de documentos. |
| `cryptography` | 48.0.0 | 50.0.0 | OpenSSL vulnerable embebido en la wheel; además `pkcs7` y validación de cadenas. Se usa para cifrar credenciales del ERP. |
| `pydantic-settings` | 2.14.1 | 2.14.2 | Lectura de secretos desde directorio. |

### Cambios

- `backend/pyproject.toml`: subir los pines.
- `uv lock` y `uv sync`.
- Revisar el bundle del instalador: `cryptography` cambia de wheel, confirmar que PyInstaller la sigue empaquetando (`installer/savi.spec`).

### Criterios de aceptación

- [ ] `uvx pip-audit` sobre el lock no reporta vulnerabilidades en paquetes que SAVI usa.
- [ ] Suite completa en verde (la subida de documentos es el camino más sensible al cambio de `starlette`/`multipart`).
- [ ] El `.exe` empaquetado arranca y `--check-config` pasa.

### Tests

Los existentes de subida de documentos alcanzan; no hace falta agregar tests nuevos, sí **correrlos** después del bump.

---

## O3 — `/health` sin tocar la base de datos

### Qué está mal

`/health` es público y ejecuta `SELECT 1`. Bajo 200 pedidos concurrentes la
mediana subió a ~1 s: es un amplificador de DoS sin credenciales.

### Cambios

**`backend/app/main.py`** (~línea 163):

- `/health` responde sin tocar la BD: estado, nombre, entorno y versión.
- Nuevo `/health/db`, **autenticado como administrador**, que hace el `SELECT 1` y reporta latencia.

```python
@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    # Sin consultar la BD a propósito: es público y sin rate limit, así que
    # cualquier chequeo costoso acá es un amplificador de DoS.
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env, "version": __version__}
```

Revisar quién consume `/health` hoy (instalador, tray, monitor) y si alguno
necesitaba la señal de BD: en ese caso apuntarlo a `/health/db`.

### Criterios de aceptación

- [ ] `/health` responde sin abrir conexión a la BD (verificable con el `echo` de SQLAlchemy o un test con engine mockeado).
- [ ] `/health/db` exige administrador y devuelve la latencia.
- [ ] Una ráfaga de 200 `/health` responde con p50 < 50 ms.

### Tests

- `test_health_does_not_touch_database`.
- `test_health_db_requires_admin`.

---

## Resultado de la fase

Al cerrar la Fase 0:

- El chat ya no puede ejecutar comandos, leer archivos ni salir a internet por su cuenta.
- No hay instalación posible con secreto por defecto fuera de desarrollo.
- Sin CVE conocidas en las dependencias que SAVI usa.
- El endpoint público más golpeado deja de tocar la base.

Queda pendiente (Fase 1 y 2): un usuario autenticado todavía puede consultar
cualquier dato del ERP y no hay límite de uso.
