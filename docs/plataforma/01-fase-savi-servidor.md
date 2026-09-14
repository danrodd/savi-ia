# Fase 1 — SAVI Servidor en la red de la empresa

> Parte de: [PRD — Plataforma SAVI](00-prd.md)
> Estado: **propuesta**.
> Depende de: nada. **Desbloquea salir a producción.**
> Alcance: `installer/`, `backend/app/launcher.py`, `backend/app/main.py`,
> módulo `auth`, módulo nuevo `server_admin`, frontend de administración.

## Resultado esperado

- [ ] El instalador ofrece los modos **Servidor**, **Escritorio** y **Acceso**.
- [ ] En modo Servidor, SAVI corre como servicio de Windows, sin bandeja ni navegador.
- [ ] Escucha en la red interna, en un puerto fijo, con regla de firewall en perfil privado.
- [ ] HTTPS con certificado PFX propio o autofirmado. HTTP permitido con aviso.
- [ ] Postgres obligatorio para la BD del agente en modo Servidor.
- [ ] Solo `api_key` / `oauth_token` para Claude en modo Servidor.
- [ ] Endurecimiento: límite de intentos de login, OpenAPI oculto en producción, headers de seguridad.
- [ ] Administración → **Servidor** (estado y avisos) y → **Sesiones** (activas y revocación).
- [ ] Logs y datos del servicio en `%ProgramData%\SAVI`.
- [ ] Actualización y respaldo documentados y probados.
- [ ] Tests unitarios y E2E. Instalación verificada en una VM limpia con Windows Server.

---

## 1. Estado actual (verificado en el código)

| Aspecto | Hoy | Dónde |
|---|---|---|
| Interfaz de red | `APP_HOST=127.0.0.1` fijo | `installer/env.template` |
| Puerto | Si está ocupado, prueba los 20 siguientes | `launcher.py` (`_resolve_port`) |
| Proceso | Ícono en la bandeja + navegador, en la sesión del usuario | `launcher.py:main`, `app/tray.py` |
| BD del agente | SQLite en `%LOCALAPPDATA%\SAVI\savi.db` por defecto; Postgres opcional | `settings.py` (`resolved_agent_db_path`) |
| Logs | `%LOCALAPPDATA%\SAVI\savi.log` | `launcher._configure_logging` |
| Límite de intentos de login | **No existe.** Solo el piso de 250 ms | `auth/application/use_cases/login.py` |
| OpenAPI (`/docs`, `/redoc`, `/openapi.json`) | **Público** en todos los entornos | `main.py:128` (FastAPI sin `docs_url=None`) |
| Headers de seguridad | **No hay** | `main.py` |
| Revocación de sesiones | `revoke` y `revoke_all_for_user` en el puerto, sin API de administración | `auth/domain/interfaces/refresh_token_repository.py` |

Nada de esto es un defecto en escritorio: con `127.0.0.1`, solo el propio
equipo llega al servidor. **Todo pasa a ser un riesgo** en cuanto SAVI
escucha en la red (R1 del PRD).

## 2. Configuración nueva

| Variable | Valores | Default | Notas |
|---|---|---|---|
| `SAVI_DEPLOYMENT_MODE` | `server` \| `desktop` | `desktop` | Un `.env` existente sin la variable sigue siendo escritorio. |
| `APP_HOST` | IP o `0.0.0.0` | `127.0.0.1` | El instalador escribe `0.0.0.0` en modo Servidor. |
| `APP_PORT` | entero | `31900` | En modo Servidor es **fijo**: no se busca otro puerto. |
| `TLS_CERT_FILE` | ruta PEM | vacío | Vacío = HTTP. |
| `TLS_KEY_FILE` | ruta PEM | vacío | Obligatoria si hay `TLS_CERT_FILE`. |
| `SAVI_PUBLIC_URL` | URL | vacío | La URL con la que entran los usuarios. Si está vacía, se calcula (§8.2). |
| `LOGIN_MAX_FAILS_PER_LOGIN` | entero | `5` | Por ventana (§6.1). |
| `LOGIN_MAX_FAILS_PER_IP` | entero | `20` | Por ventana. |
| `LOGIN_FAIL_WINDOW_MINUTES` | entero | `15` | Duración de la ventana y del bloqueo. |

### 2.1 Validaciones al construir `Settings` (modo `server`)

Todas fallan al arrancar con un mensaje en español y con qué corregir.
`--check-config` las muestra igual:

| Regla | Mensaje |
|---|---|
| `agent_db_engine` debe ser `postgresql` | "En modo servidor el historial debe estar en PostgreSQL…" |
| `jwt_secret` distinto de `change-me-in-prod` y con al menos 32 caracteres | "JWT_SECRET no es seguro…" |
| `app_debug` en `false` | "APP_DEBUG debe estar desactivado en modo servidor." |
| Si hay `TLS_CERT_FILE`, existen los dos archivos y son legibles | "No se puede leer el certificado…" |

**Por qué fallar y no advertir:** un servidor de red mal configurado que
arranca igual queda expuesto hasta que alguien lea el log. En escritorio
estas reglas no aplican, para no romper instalaciones existentes.

## 3. Instalador

### 3.1 Página nueva: modo de instalación

Primera página del asistente, después de la bienvenida:

| Opción | Texto de ayuda |
|---|---|
| **Servidor de la empresa** (recomendada) | "Se instala una sola vez, en un equipo siempre encendido de la red. Los usuarios entran desde su navegador." |
| **Escritorio** | "Para agentes de soporte que atienden varios clientes desde su propio equipo." |
| **Acceso a un servidor existente** | "Solo crea el acceso directo al SAVI de tu empresa. No instala el servidor." |

### 3.2 Pasos por modo

| Paso | Servidor | Escritorio | Acceso |
|---|---|---|---|
| Requisitos (CLI, Git) | Solo si el proveedor elegido es Claude | Como hoy | — |
| BD del ERP | Sí | Sí | — |
| BD de SAVI | **Solo PostgreSQL**. Botón "Probar", y opción "Crear la base si no existe" (`CREATE DATABASE`, requiere permiso). | Como hoy | — |
| Proveedor de IA | Claude con clave o token, Gemini u OpenAI con clave. **Sin "iniciar sesión"** (R3). Se puede omitir y configurar después en la interfaz. | Como hoy | — |
| Red | Puerto (default `31900`), certificado (§4) y regla de firewall | Puerto | URL del servidor + "Probar" |
| Administradores | `SAVI_ADMIN_LOGINS`, con precarga opcional del usuario ERP de quien instala | Como hoy | — |
| Vinculación con Cloud | Token opcional (Fase 2) | Opcional (Fase 2) | — |

### 3.3 Qué genera el modo Servidor

| Artefacto | Ubicación | Permisos |
|---|---|---|
| Aplicación | `C:\Program Files\SAVI\` | Lectura para el servicio |
| `.env` | `C:\Program Files\SAVI\.env` | Administradores y cuenta del servicio: lectura. Solo administradores escriben. |
| Datos, logs y certificados | `C:\ProgramData\SAVI\` (`logs\`, `tls\`) | `tls\`: solo administradores y cuenta del servicio. |
| Servicio | `SAVI`, inicio automático (retrasado) | Ver §5 |
| Regla de firewall | `SAVI (TCP <puerto>)`, entrada, **perfil Privado y Dominio**, sin Público | `netsh advfirewall firewall add rule …` |
| Accesos directos | "Abrir SAVI" (URL), "Diagnosticar SAVI", "Reiniciar servicio SAVI" | Todos los usuarios |

### 3.4 Modo Acceso

- Pide la URL (`https://servidor:31900`) y la prueba con `GET /version`,
  mostrando la versión encontrada.
- Crea un acceso directo `.url` en el escritorio y en el menú Inicio.
- Si el servidor usa certificado autofirmado, ofrece **"Confiar en el
  certificado de este servidor"**. Lo descarga de `GET /server/certificate`
  (§4.3) y lo instala en `LocalMachine\Root`, con elevación. La
  alternativa recomendada para muchas PCs es GPO (§10).
- No instala Python, Node, Git ni nada del backend.

### 3.5 Actualización

- Detecta el modo instalado leyendo `SAVI_DEPLOYMENT_MODE` del `.env`
  existente y **no** vuelve a preguntar.
- Modo Servidor: `SAVI-service.exe stop` → reemplazo de archivos →
  `start`. Las migraciones corren al arrancar (`ensure_schema`, como
  hoy). No hace falta `CloseApplications=force`, porque el servicio se
  detiene de forma ordenada.
- Mantiene `.env`, `tls\` y logs.

## 4. HTTPS en la red interna

### 4.1 Opciones del asistente

| Opción | Qué hace |
|---|---|
| **Certificado de la empresa (PFX)** | Pide archivo y contraseña. Lo convierte a `tls\cert.pem` + `tls\key.pem` con `SAVI.exe --import-pfx`. |
| **Generar certificado autofirmado** (default) | `SAVI.exe --generate-cert --hosts <nombre-equipo>,<fqdn>,<IPs>`: RSA 2048, SAN con todos los nombres, validez de 825 días. Exporta además `tls\savi-servidor.cer` para distribuir. |
| **Sin HTTPS** | Permitido, pero la interfaz de administración muestra el aviso permanente `http_without_tls` (§8.2). |

### 4.2 Implementación

- `uvicorn.Config(ssl_certfile=…, ssl_keyfile=…)` cuando hay
  `TLS_CERT_FILE`. No se agrega proxy inverso: una dependencia menos que
  instalar y mantener en el servidor del cliente.
- Generación y conversión con `cryptography`, que ya es dependencia
  transitiva (D4 de multi-BD).
- `--generate-cert` descubre los nombres con `socket.gethostname()`,
  `socket.getfqdn()` y las IPv4 de `socket.getaddrinfo(hostname)`, sin
  loopback.
- Renovación: `SAVI.exe --generate-cert` sobre una instalación existente
  regenera y reinicia el servicio. Administración avisa 30 días antes del
  vencimiento (`cert_expiring`).

### 4.3 `GET /server/certificate`

- Público, sin autenticación. Devuelve el `.cer` **público** (DER),
  `Content-Disposition: attachment`.
- Solo existe si `SAVI_DEPLOYMENT_MODE=server` y el certificado es
  autofirmado. Si no, `404`.
- Se agrega `"server"` a `_API_PREFIXES` (`main.py:56`).

## 5. Servicio de Windows

### 5.1 Decisión: WinSW

| Opción | Evaluación |
|---|---|
| **WinSW** (binario MIT, configuración XML) | **Elegida.** Un `.exe` junto a `SAVI.exe`, rotación de logs propia, recuperación ante fallos, sin tocar el empaquetado de PyInstaller. |
| `pywin32` + `servicemanager` | Obliga a reestructurar el entrypoint y suma trampas de PyInstaller con servicios. |
| NSSM | Sin mantenimiento activo. |

`installer/service/SAVI-service.xml`:

```xml
<service>
  <id>SAVI</id>
  <name>SAVI</name>
  <description>Asistente virtual SAVI de SEO Group</description>
  <executable>%BASE%\SAVI.exe</executable>
  <arguments>--service</arguments>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <onfailure action="restart" delay="60 sec"/>
  <resetfailure>1 hour</resetfailure>
  <stoptimeout>20 sec</stoptimeout>
  <log mode="roll-by-size"><sizeThreshold>5120</sizeThreshold><keepFiles>3</keepFiles></log>
  <serviceaccount><username>NT SERVICE\SAVI</username></serviceaccount>
</service>
```

- **Cuenta virtual `NT SERVICE\SAVI`:** sin contraseña que administrar y
  con privilegios mínimos. Es la cuenta a la que se le dan permisos en
  §3.3.
- **Verificación obligatoria antes de cerrar la fase:** que el subproceso
  `claude` del SDK arranque bajo esa cuenta (necesita un `HOME`
  escribible y Git Bash). Si no arranca, la alternativa documentada es
  `LocalService` con `CLAUDE_CONFIG_DIR` apuntando a
  `%ProgramData%\SAVI\claude`. Gemini y OpenAI no tienen esa dependencia.

### 5.2 `SAVI.exe --service`

Modo nuevo en `launcher.py:main`:

| Aspecto | `--service` | Escritorio (sin cambios) |
|---|---|---|
| Consola, splash, bandeja, navegador | No | Sí |
| Puerto ocupado | Falla con log claro y código de salida ≠ 0. WinSW reintenta. | Busca otro puerto |
| Logs | `%ProgramData%\SAVI\logs\savi.log` (misma rotación de 5 MB × 3) | `%LOCALAPPDATA%` |
| Señal de parada | `SIGTERM`/`CTRL_BREAK` → `server.should_exit = True` y cierre ordenado | Menú de la bandeja |
| `workers` de uvicorn | **1**, fijo y documentado | 1 |

**Por qué un solo worker:** el registry de engines del ERP, la caché del
proveedor activo, el límite de intentos (§6.1) y el sincronizador de la
Fase 2 viven en memoria del proceso. Varios workers romperían esos
supuestos sin dar ningún error. Un proceso async atiende con holgura a los
usuarios de una empresa, porque el trabajo pesado es I/O contra el ERP y
el proveedor.

`data_dir()` pasa a devolver `%ProgramData%\SAVI` cuando
`SAVI_DEPLOYMENT_MODE=server`. Afecta a logs y a cualquier escritura
local. El SQLite no aplica, porque es obligatorio Postgres.

## 6. Endurecimiento para red

### 6.1 Límite de intentos de login

`auth/infrastructure/security/login_throttle.py`, detrás de un puerto
`LoginThrottle` en `auth/domain/interfaces/`:

```python
class LoginThrottle(ABC):
    def check(self, *, login_key: str, ip: str) -> None: ...        # levanta TooManyLoginAttemptsError
    def register_failure(self, *, login_key: str, ip: str) -> None: ...
    def register_success(self, *, login_key: str, ip: str) -> None: ...  # limpia el contador del login
```

- Implementación en memoria, con ventana deslizante y `asyncio.Lock`.
  Suficiente con un proceso (§5.2).
- `login_key` es el login **tal como se escribió**, normalizado
  (`strip().upper()`, incluido `@CODIGO`). No se consulta si existe: el
  bloqueo se aplica igual a un login inexistente, así no se vuelve un
  oráculo de usuarios.
- `LoginUseCase.execute` llama a `check` **antes** de autenticar,
  `register_failure` ante `InvalidCredentialsError` y `register_success`
  al emitir tokens.
- Respuesta: `429`, `errorCode: "too_many_login_attempts"`, header
  `Retry-After` con los segundos restantes, y mensaje "Demasiados intentos
  fallidos. Probá de nuevo en N minutos."
- IP: `request.client.host`. **No** se lee `X-Forwarded-For`: en modo
  Servidor no hay proxy, y aceptarlo permitiría falsear la IP para
  evadir el límite.
- Aplica en los dos modos. En escritorio no molesta a nadie y protege
  igual.

### 6.2 OpenAPI

`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` cuando
`app_env == "production"`. En desarrollo sigue igual. Se quitan `docs`,
`redoc` y `openapi.json` de `_API_PREFIXES` solo en ese caso, para que la
SPA no los intercepte de forma confusa.

### 6.3 Headers de seguridad

Middleware `app/infrastructure/http/security_headers.py`:

| Header | Valor |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `same-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Strict-Transport-Security` | `max-age=31536000` **solo con TLS** |
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'` |

- La CSP entra primero como **`Content-Security-Policy-Report-Only`** y se
  valida con el build real: mermaid y echarts pueden requerir ajustes. Se
  promueve a CSP efectiva cuando la consola del navegador queda limpia en
  el E2E completo.
- `frame-ancestors` se vuelve configurable en la Fase 4, si el ERP embebe
  con iframe. Con WebView2 no hace falta.

### 6.4 CORS

En modo Servidor el frontend se sirve desde el mismo origen, así que
`CORS_ALLOWED_ORIGINS` queda **vacío** por defecto y no se registra el
middleware (`main.py:135` ya lo condiciona). Evita el
`allow_credentials=True` con orígenes de desarrollo en un servidor
productivo.

## 7. Sesiones activas

### 7.1 Modelo

Columna nueva en `refresh_tokens`: `last_used_at: UtcDateTime NULL`.
`RefreshUseCase` la actualiza en cada refresh. Con access tokens de 15
minutos, es una aproximación honesta de "última actividad". Migración
Alembic con batch mode, sin backfill (`NULL` = sin refrescar todavía).

### 7.2 API (`SaviAdminDep`)

| Método | Ruta | Respuesta |
|---|---|---|
| `GET` | `/admin/sessions` | Sesiones no revocadas y no vencidas: `jti`, `user_login`, `erp_database_name`, `created_at`, `last_used_at`, `expires_at`. Ordenadas por `last_used_at` desc. |
| `POST` | `/admin/sessions/{jti}/revoke` | `204`. Idempotente. |
| `POST` | `/admin/sessions/revoke-user` | Body `{erp_database_id, user_id}`. `204`. Usa `revoke_all_for_user`. |

- Nunca se devuelve el token, solo el `jti`.
- **Límite dicho en voz alta:** revocar corta el refresh, pero el access
  token vigente sigue válido hasta 15 minutos. La UI lo aclara ("La
  sesión se cierra en un máximo de 15 minutos"). Una lista de revocación
  de access tokens queda fuera de alcance.
- Sirve también en escritorio (Postgres compartido), así que no se
  condiciona por modo.

## 8. Estado del servidor

### 8.1 `GET /admin/server-status` (`SaviAdminDep`)

```json
{
  "deployment_mode": "server",
  "version": "v1.2.0",
  "listen": { "host": "0.0.0.0", "port": 31900, "tls": true },
  "access_urls": ["https://SRV-FARMX:31900", "https://192.168.1.20:31900"],
  "tls": { "subject": "CN=SRV-FARMX", "self_signed": true, "expires_at": "2028-12-18T00:00:00Z" },
  "agent_db": { "engine": "postgresql", "host": "localhost", "name": "savi_agente", "reachable": true },
  "started_at": "2026-09-14T08:00:00Z",
  "active_sessions": 12,
  "erp_databases": { "total": 3, "usable": 3 },
  "llm_provider": { "provider": "claude", "credential_kind": "api_key", "usable": true },
  "warnings": [ { "code": "http_without_tls", "severity": "warning" } ]
}
```

Nunca incluye usuarios, contraseñas ni claves.

### 8.2 Avisos (`warnings`)

| `code` | Condición | Severidad |
|---|---|---|
| `http_without_tls` | Modo Servidor sin TLS | warning |
| `cert_expiring` | Vence en 30 días o menos | warning |
| `cert_expired` | Vencido | error |
| `erp_db_password_in_env` | `ERP_DB_PASSWORD` sigue con valor (pendiente §13.6 de multi-BD) | info |
| `local_session_in_server` | Proveedor Claude con `local_session` en modo Servidor | error |
| `no_llm_provider` | Ningún proveedor utilizable | error |
| `public_url_unset` | Sin `SAVI_PUBLIC_URL` y más de una IP detectada | info |

`access_urls` usa `SAVI_PUBLIC_URL` si está definida. Si no, la calcula
como en §4.2.

### 8.3 Validación de proveedor en modo Servidor

`llm_providers`: guardar o activar Claude con `credential_kind =
local_session` cuando `SAVI_DEPLOYMENT_MODE=server` → `422` "En modo
servidor Claude requiere clave de API o token". La UI oculta esa opción
en ese modo (`GET /version` o `server-status` expone el modo).

## 9. Frontend

### 9.1 Navegación de Administración

`AdminLayout.vue` suma dos ítems:

| Ítem | Ruta | Ícono (`lucide-vue-next`) |
|---|---|---|
| Servidor | `/admin/servidor` (`admin-server`) | `Server` |
| Sesiones | `/admin/sesiones` (`admin-sessions`) | `Users` |

### 9.2 `ServerStatusView.vue`

- Tarjeta **"Cómo entran los usuarios"**: las `access_urls`, cada una con
  botón de copiar. Con autofirmado, el enlace "Descargar certificado para
  las PCs" (`/server/certificate`) y una nota breve sobre GPO.
- Tarjetas de estado: servicio (versión, arrancado hace…), BD de SAVI,
  certificado, bases del ERP y proveedor de IA.
- Lista de avisos con texto de acción por `code`.
- **Fallback del botón copiar:** la API de portapapeles exige contexto
  seguro. Sobre HTTP se usa selección de texto y se avisa ("Copiá con
  Ctrl+C").

### 9.3 Banner global de administración

Si hay avisos de severidad `error`, o `http_without_tls`, `AdminLayout`
muestra un banner arriba del contenido con enlace a
`/admin/servidor`. Solo lo ven los administradores.

### 9.4 `SessionsView.vue`

- Tabla: usuario, sucursal, inició, última actividad, vence, y acción
  "Cerrar sesión". Además, "Cerrar todas las sesiones de este usuario".
- Diálogo de confirmación con la aclaración de los 15 minutos (§7.2).
- La propia sesión del administrador se marca "(esta sesión)" y pide
  doble confirmación.

### 9.5 Formulario de proveedor

`LlmProviderFormDialog.vue`: si el modo es `server`, oculta
`local_session` en las opciones de credencial de Claude.

### 9.6 Login

Con `429 too_many_login_attempts`, muestra el mensaje del backend y
desactiva el botón hasta que vence `Retry-After`, con cuenta regresiva.
El mensaje genérico de credenciales inválidas no cambia.

## 10. Operación (documentación nueva: `installer/SERVIDOR.md`)

1. **Requisitos del servidor:** Windows Server 2019+ o Windows 10/11
   Pro siempre encendido, 4 GB de RAM libres, PostgreSQL 14+ (puede ser el
   mismo del ERP), y conectividad con las bases del ERP y con el
   proveedor de IA.
2. **Instalación paso a paso**, con capturas.
3. **Distribuir el certificado por GPO:** *Configuración del equipo →
   Directivas → Configuración de Windows → Configuración de seguridad →
   Directivas de clave pública → Entidades de certificación raíz de
   confianza → Importar* `savi-servidor.cer`.
4. **Respaldo:** `pg_dump -Fc savi_agente` diario + copia de `.env` y de
   `ProgramData\SAVI\tls\`. Sin `ERP_CREDENTIALS_KEY`, las contraseñas de
   las bases quedan ilegibles (D4).
5. **Restauración** en otro equipo: instalar en modo Servidor →
   restaurar `.env` y `tls\` → `pg_restore` → iniciar servicio.
6. **Diagnóstico:** `SAVI.exe --check-config` (ahora informa modo,
   servicio, puerto en uso, certificado y firewall) y logs en
   `ProgramData`.
7. **Migrar desde instalaciones de escritorio:** exportar bases desde una
   PC (función existente) e importarlas en el servidor. **El historial de
   chats por PC no se migra**, queda fuera de alcance y documentado.

## 11. Tests

### 11.1 Backend (pytest)

| Test | Verifica |
|---|---|
| `Settings` en `server` | Rechaza SQLite, `jwt_secret` por defecto, `app_debug=true` y TLS con archivos inexistentes. `desktop` no aplica esas reglas. |
| Límite por login | El 6.º intento fallido devuelve `429` con `Retry-After`. Un login exitoso limpia el contador. Un login inexistente se bloquea igual. |
| Límite por IP | 20 fallos con logins distintos desde la misma IP → `429`. |
| Sin `X-Forwarded-For` | Un header falseado no evade el límite. |
| OpenAPI | `production` → `/docs`, `/redoc` y `/openapi.json` dan `404`; `development` → `200`. |
| Headers | Presentes en API y SPA. HSTS solo con TLS. |
| Sesiones | Lista excluye revocadas y vencidas. Revocar es idempotente. `revoke-user` revoca solo las de ese par `(base, usuario)`. Ningún response incluye el token. `403` sin admin. |
| `last_used_at` | Se actualiza en refresh. |
| `server-status` | Avisos calculados para cada condición de §8.2. No contiene secretos (test que busca `password`, `key`, `secret` y `token` en el JSON). |
| Proveedor | `local_session` en `server` → `422`. |
| Certificado | `--generate-cert` produce SAN con todos los nombres. `/server/certificate` es `404` fuera de modo Servidor o con certificado propio. |
| Launcher `--service` | Puerto ocupado → código de salida ≠ 0, sin probar otros puertos (con puerto ocupado simulado). |
| Migración | `refresh_tokens.last_used_at` en SQLite y Postgres. |

### 11.2 Frontend (Vitest)

- `ServerStatusView`: render de avisos por `code` y fallback del botón
  copiar sin contexto seguro.
- `SessionsView`: confirmación y doble confirmación para la propia
  sesión.
- `LoginView`: cuenta regresiva con `429`.
- `LlmProviderFormDialog`: sin `local_session` en modo `server`.

### 11.3 E2E y verificación real

- Playwright contra un backend con `SAVI_DEPLOYMENT_MODE=server`, TLS
  autofirmado (`ignoreHTTPSErrors`) y Postgres:
  1. Login y chat.
  2. Administración → Servidor muestra las URLs.
  3. Un segundo contexto de navegador inicia sesión; el primero la ve en
     Sesiones y la revoca; el segundo es expulsado al siguiente refresh.
  4. Bloqueo de login tras 5 fallos.
- **VM limpia con Windows Server** (obligatorio para cerrar la fase):
  1. Instalar en modo Servidor con certificado autofirmado.
  2. Reiniciar la VM y confirmar que el servicio levanta solo.
  3. Desde otra VM de la misma red: instalar en modo Acceso con
     "Confiar en el certificado", entrar y chatear.
  4. Confirmar que desde una red Pública de Windows el puerto **no**
     responde.
  5. Actualizar a un build nuevo y confirmar que el historial y las
     sesiones siguen.
  6. Verificar el subproceso `claude` bajo `NT SERVICE\SAVI` (§5.1).

Gates: `uv run lint`, `uv run typecheck`, `uv run pytest`,
`npm run type-check`, `npm run check`, `npx vitest run`,
`npx playwright test`.
