# Revisión general de SAVI

> Fecha: 2026-09-15 · Alcance: backend, frontend, dependencias y UX.
> Versión revisada: `a24ab2a` (sobre v1.1.0).
> Cada hallazgo de seguridad se **verificó en ejecución** contra el entorno de
> desarrollo, sin escribir datos, salvo donde dice "por lectura de código".

## Resumen ejecutivo

SAVI está **bien construido en lo que más cuesta**:

- arquitectura hexagonal consistente;
- ownership de conversaciones correcto en todas las rutas;
- `consultar_datos` sin inyección SQL;
- markdown sanitizado;
- credenciales cifradas;
- 432 tests con Pyright strict.

> **Estado al 2026-09-15:** las Fases 0 a 3 están implementadas y verificadas,
> y la 4 va parcial. **Corregidos: el hallazgo crítico, los 6 altos y 11 de los
> 13 medios.** Queda M9 (unificar el bucle agéntico, a la espera de una key de
> OpenAI para poder probarlo de punta a punta) y pulido de interfaz.
>
> La verificación destapó además **tres bugs que esta revisión no había visto**,
> porque solo aparecen con la SPA compilada que sirve el backend: la CSP rompía
> la app instalada, todas las pantallas `/admin/*` devolvían un 404 JSON al
> recargarlas, y una barra de avance se dibujaba en documentos ya terminados.
> Están en [`seguridad/05-fase-4-deuda-y-ux.md`](seguridad/05-fase-4-deuda-y-ux.md).

Pero tiene **dos problemas de seguridad que hay que corregir antes de
cualquier despliegue con usuarios reales**:

1. **El chat con Claude expone Bash, lectura y escritura de archivos y acceso web** en la máquina donde corre SAVI, sin pedir permiso. Es un fix de una línea.
2. **Cualquier usuario puede consultar cualquier dato del ERP con SQL libre**, sin importar sus permisos del ERP, y la conexión es de **superusuario de Postgres**.

| Severidad | Cantidad |
|---|---|
| Crítica | 1 |
| Alta | 6 |
| Media | 13 |
| Baja | 8 |

Incluye la sección **Seguridad operativa** (carga, ataques, timeouts), medida
con el backend en ejecución.

## Crítica

### C1. El agente de Claude tiene Bash, Read, Write y WebFetch con permisos automáticos

> **Corregido el 2026-09-15.** `tools=[]` más `disallowed_tools` en el runner y
> en el generador de títulos. Verificado contra el CLI: de 31 herramientas
> integradas a **0**, y el contexto por turno bajó de ~144.000 a ~31.000
> tokens. Ver [`seguridad/01-fase-0-cierre-urgente.md`](seguridad/01-fase-0-cierre-urgente.md).

| | |
|---|---|
| **Dónde** | `backend/app/modules/chat/infrastructure/llm/claude/runner.py:89-95` y `claude/title_generator.py:27-31` |
| **Qué pasa** | Se pasa `permission_mode="bypassPermissions"` y `allowed_tools=[…]`, pero no `tools`. En el Agent SDK, `allowed_tools` solo **aprueba sin preguntar**; el conjunto disponible lo define `tools`, y si falta el CLI carga **todas** sus herramientas. |
| **Verificado** | Con las opciones reales del chat, el mensaje `init` del CLI lista 31 herramientas integradas, entre ellas `Bash`, `Read`, `Write`, `Edit`, `WebFetch`, `WebSearch` y `Task`, con `permissionMode: bypassPermissions`. No se ejecutó ninguna. |
| **Escenario** | Un usuario autenticado cualquiera escribe en el chat: *"usá Bash para mostrarme el archivo .env"*. Obtiene `ERP_CREDENTIALS_KEY` y `JWT_SECRET`, con lo que puede descifrar todas las contraseñas del ERP y firmarse tokens de administrador. También podría ejecutar comandos, escribir archivos o sacar datos por `WebFetch`. La única barrera es que el modelo se niegue, y eso no es un control de seguridad. |
| **Efecto secundario** | Inflan el costo. Con Claude cada respuesta usa **~144.000 tokens de contexto** contra ~15.000 con Gemini (medido sobre 31 respuestas reales, ~USD 0,14 cada una). Probablemente también explican el modo "deferred tools / ToolSearch" que CLAUDE.md atribuye a tener más de 4 tools MCP. |
| **Corrección** | `tools=[]` en las dos opciones (chat y títulos), más `disallowed_tools` con las integradas como segunda barrera. Test que verifique las opciones construidas. Medir de nuevo tokens por respuesta y revisar si la regla de "máximo 4 tools" sigue siendo necesaria. |

## Altas

### A1. SQL libre sin control de permisos del ERP

- **Dónde:** `chat/infrastructure/llm/tools/registry.py:176-202`.
- **Qué pasa:**
  - `consultar_libre` y `consultar_datos` se entregan a **todos los usuarios**.
  - `allowed_modules` solo filtra `consultar_conocimiento`, con la documentación y los documentos de la empresa.
- **Escenario:** un usuario con acceso solo a Ventas pregunta *"¿cuánto gana cada empleado?"* y SAVI consulta la nómina con SQL libre.
- **Corrección:** decidir el modelo de permisos de datos. Opciones:
  - no ofrecer `consultar_libre` a quien no es administrador;
  - una lista de esquemas y tablas permitidos por módulo, validada en el AST con `sqlglot`;
  - un usuario de Postgres por perfil con `GRANT` restringidos.

### A2. Conexión al ERP como superusuario y funciones peligrosas permitidas

- **Dónde:** `free_query/application/sql_validator.py` y la configuración de cada base del ERP.
- **Verificado:** estas consultas **pasan el validador y se ejecutan** contra el ERP de desarrollo:

| Consulta | Resultado |
|---|---|
| `SELECT current_setting('is_superuser')` | `on` (usuario `postgres`) |
| `SELECT pg_read_file('postgresql.conf', …)` | Lee archivos del servidor de BD |
| `SELECT count(*) FROM pg_shadow …` | Accede a los hashes de contraseñas de Postgres |
| `SELECT pg_cancel_backend(…)` | Se ejecuta. `pg_terminate_backend` podría cortar **todas las conexiones del ERP** (no se probó) |
| `SELECT pg_sleep(…)` | Retiene la conexión hasta el `statement_timeout` (60 s) |
| Extensiones | `dblink` y `postgres_fdw` están instaladas |

- **Qué sí resiste:** el modo solo lectura. Un `set_config('default_transaction_read_only','off')` se revierte con el rollback de la transacción (verificado), y cambiar `transaction_read_only` falla. No se encontró forma de **escribir** datos.
- **Corrección:**
  - Validador: lista de funciones permitidas, o como mínimo bloquear `pg_*`, `set_config`, `dblink*`, `lo_*`, `current_setting` y los catálogos `pg_shadow`, `pg_authid` y `pg_stat_activity`. Agregar tests.
  - Instalación: documentar y recomendar un rol de solo lectura sin superusuario (`CREATE ROLE savi_lectura … ; GRANT SELECT …`). Advertir en la pantalla de bases si el usuario configurado es superusuario.

### A3. El administrador de una base administra todas

- **Dónde:** `auth/infrastructure/http/admin.py:28`.
- **Qué pasa:** `is_savi_admin` es `user.is_admin`, es decir, administrador del ERP **en la base con la que inició sesión**. Ese usuario puede:
  - ver y modificar las conexiones de **todas** las bases;
  - exportarlas con contraseña (incluye las contraseñas de todos los clientes);
  - cambiar las keys de IA;
  - gestionar documentos de todas las empresas.
- **Contexto:** en la instalación de escritorio de un agente de soporte esto puede ser aceptable. En una instalación con varias empresas, y sobre todo en **SAVI Servidor** (`docs/plataforma/`), rompe el aislamiento entre clientes.
- **Corrección:** limitar la administración global a `SAVI_ADMIN_LOGINS` o a la base por defecto, y definir el alcance antes de la Fase 1 de plataforma.

### A4. Sin límite de intentos ni de uso

- **Login:** solo hay un piso de 250 ms por intento fallido (contra la enumeración por tiempo), pero no hay límite de intentos ni bloqueo. Las contraseñas del ERP son MD5 sin sal, así que la fuerza bruta por la API es viable.
- **Chat:** no hay límite por usuario. Con ~USD 0,14 por respuesta en Claude, un script con un token válido genera costo sin techo.
- **Corrección:** rate limit por IP y login en `/auth/login`, con bloqueo temporal. Límite de turnos por usuario y minuto en `/chat`, que se conecta después con los créditos de plataforma.

## Medias

| # | Hallazgo | Dónde | Evidencia | Corrección |
|---|---|---|---|---|
| M1 | **Módulos de la interfaz calculados contra la base por defecto.** `/auth/me/bootstrap` y `/me/modules-version` usan `get_erp_engine_for(None)`: un usuario de otra base ve los módulos del usuario con el **mismo id numérico** en la base por defecto. El chat sí lo resuelve bien. | `auth/infrastructure/http/dependencies.py:132-145` | Lectura de código; el chat usa `ResolveModulesForDatabaseUseCase` y bootstrap no. | Usar el resolvedor por base, con la base del token. |
| M2 | **`JWT_SECRET` por defecto aceptado.** Si falta en el `.env`, se usa `"change-me-in-prod"` sin aviso, y cualquiera puede firmar tokens de administrador. El instalador lo genera, pero una instalación manual o un `.env` roto quedan expuestos. | `infrastructure/config/settings.py:145` | Lectura de código. | Negarse a arrancar con el valor por defecto fuera de `development`. |
| M3 | **Dependencias con CVE.** `starlette 1.1.0` y `python-multipart 0.0.29` (DoS al parsear formularios; SAVI recibe archivos multipart), `cryptography 48.0.0` (OpenSSL empaquetado), `pydantic-settings 2.14.1`. | `backend/uv.lock` | `pip-audit`. | Actualizar a `starlette ≥ 1.3.1`, `python-multipart ≥ 0.0.31`, `cryptography ≥ 50`, `pydantic-settings ≥ 2.14.2`. |
| M4 | **Fronteras de seguridad sin tests.** `free_query` (validador de SQL) y `data_query` (compilador) no tienen ningún test. | `backend/tests/` | Búsqueda sin coincidencias. | Tests del validador con casos maliciosos (los de A2) y del compilador. |
| M5 | **Turnos concurrentes en la misma conversación.** No hay bloqueo. Dos pestañas o un doble envío pueden correr `send`/`edit_last`/`regenerate` a la vez y dejar ramas cruzadas. | `chat/application/use_cases/chat_turn.py` | Lectura de código; no reproducido. | Bloqueo por conversación (fila con `FOR UPDATE` o lock en proceso) y 409 si hay un turno en curso. |
| M6 | **Costo invisible sin tarifa.** Si el administrador no carga la tarifa de un modelo, el costo queda `NULL` y la pantalla de consumo lo suma como 0. | `chat/infrastructure/llm/pricing.py:6` | Las 11 respuestas con Gemini registran USD 0. | Marcar "sin tarifa" en consumo y avisar al activar un proveedor sin precios. |
| M7 | **El error de una herramienta llega crudo al modelo.** `f"La herramienta falló: {e}"` puede incluir detalles internos (host, SQL, rutas) que luego el modelo repite al usuario. | `chat/infrastructure/llm/tools/registry.py:150` | Lectura de código. | Mensaje genérico hacia el modelo y detalle solo en el log. |
| M8 | **Interfaz de documentos:** sin avance en documentos largos, acciones ocultas en móvil y soltar un archivo fuera de la zona abre el archivo en el navegador. | `frontend/src/modules/admin/` | Ver [`revision-interfaz.md`](../backend/docs/company_knowledge/revision-interfaz.md). | Ya priorizado ahí. |
| M9 | **Tres runners con el mismo bucle agéntico.** OpenAI y Gemini reimplementan el ciclo tool → resultado → modelo, con el truncado y el costo duplicados. Cada cambio de comportamiento se hace tres veces. | `chat/infrastructure/llm/{openai,gemini}/runner.py` | 366 y 313 líneas con estructura paralela. | Extraer el bucle a una clase común y dejar en cada runner solo la traducción del proveedor. |

## Bajas

| # | Hallazgo | Detalle |
|---|---|---|
| B1 | Tokens en `localStorage` | El refresh token (7 días) queda en `localStorage`. Con el sanitizado actual el riesgo es bajo; una cookie `HttpOnly` lo eliminaría. |
| B2 | `xlsx 0.18.5` con 2 CVE altas sin parche en npm | SAVI solo **escribe** Excel y las fallas son de lectura: no explotable hoy. Migrar a la distribución oficial de SheetJS o a `exceljs` si algún día se leen archivos. |
| B3 | Sin Content-Security-Policy | Agregar una CSP al servir el frontend sería defensa en profundidad. |
| B4 | El historial carga todos los mensajes de la conversación en cada turno | `list_messages` trae todo y después se usan los últimos 20. En conversaciones largas es trabajo de más; conviene un `LIMIT` en SQL. |
| B5 | `launcher.py` tiene 1.145 líneas | Es el archivo más grande del backend; conviene partirlo por responsabilidad. |
| B6 | `sql_validator.py` con `# pyright: basic` | Único archivo fuera de strict, y es justo una frontera de seguridad. |
| B7 | UX: conversaciones con títulos casi idénticos y "Nueva conversación" vacías acumuladas | Sin buscador de conversaciones. El consumo por usuario muestra `#1` en lugar del nombre. |

## Seguridad operativa: carga, ataques, timeouts

Esta sección se agregó tras probar el backend **en ejecución** con ráfagas
concurrentes contra el entorno de desarrollo.

### O1. (Alta) No hay rate limiting en ningún endpoint

- **Verificado:** 50 logins fallidos lanzados en paralelo se procesaron **todos** (50 × 401), sin bloqueo ni demora creciente. Una ráfaga de 200 `/health` se aceptó a 142 req/s.
- **Consecuencia:**
  - **Fuerza bruta de contraseñas.** Las del ERP son MD5 sin sal; sin límite de intentos, probar millones de contraseñas por la API es viable.
  - **Abuso del chat.** Un token válido puede disparar respuestas sin techo, cada una ~USD 0,14 en Claude (ver C1/A4).
- **Corrección:** rate limit por IP y por login en `/auth/login` (con bloqueo temporal escalonado), y por usuario en `/chat`. `slowapi` o un middleware propio con contador en memoria alcanza para la app de escritorio; para SAVI Servidor, un store compartido.

> **Corrección al hallazgo A4 sobre enumeración por tiempo:** medido **en frío y secuencial**, los tres caminos de login fallido tardan casi lo mismo (cliente inexistente 270 ms, usuario inexistente 264 ms, contraseña mala 258 ms). El piso de 250 ms **funciona bien** y la enumeración por tiempo **está mitigada**. Lo que falta es el límite de intentos, no la defensa temporal.

### O2. (Alta) Sin tope de turnos de chat concurrentes → agotamiento de recursos

- **Verificado por código:** no hay ningún `Semaphore` ni límite de concurrencia en todo el backend. Cada turno de chat con Claude lanza un proceso `claude.exe` propio y monta un MCP server en el proceso.
- **Consecuencia:** N usuarios simultáneos = N subprocesos `claude.exe`, cada uno con **~144.000 tokens de contexto** (ver C1). Una decena de turnos a la vez satura CPU y memoria de la máquina. En la app de escritorio (un usuario) no importa; en **SAVI Servidor** con varios usuarios es un cuello de botella y una vía de DoS trivial.
- **Corrección:** un semáforo global de turnos en curso (rechazar con 429 al superarlo) y, en plataforma, una cola con concurrencia acotada.

### O3. (Media) `/health` sin autenticación golpea la base de datos

- **Verificado:** `/health` ejecuta `SELECT 1` contra la BD del agente. Bajo 200 pedidos concurrentes, la mediana subió a ~1 s (con SQLite las conexiones se serializan).
- **Consecuencia:** un endpoint público que toca la BD es un **amplificador de DoS**: floodearlo satura la conexión del agente y degrada toda la app, sin necesidad de credenciales.
- **Corrección:** que `/health` responda sin tocar la BD (o un `/health/db` separado y autenticado), y que quede detrás del rate limit.

### O4. (Media) Un turno de chat no tiene tope de tiempo

- **Verificado por código:** el único límite es `max_agent_turns=40` (rondas de herramienta). No hay reloj de pared: un turno puede encadenar 40 llamadas a herramientas y durar mucho, reteniendo el subproceso, la conexión SSE y —con SQLite— una transacción abierta todo ese tiempo (ver O6). El `asyncio.timeout` que existe es solo para la fase 2 del auto-título (4 s), no para el turno.
- **Corrección:** un timeout de pared por turno que corte el stream con un mensaje claro.

### O5. (Media) La ingesta de documentos es un solo worker, en serie

- Ya señalado en [`validacion-importacion.md`](../backend/docs/company_knowledge/validacion-importacion.md): los documentos se procesan de a uno. Un PDF de 500 páginas (~1 min 45 s) **bloquea la cola** de todos los demás. La búsqueda de documentos, además, corre en un pool de solo 2 hilos compartido por todos los chats.
- **Corrección:** avanzar en la interfaz (avance + posición en cola) y, si SAVI Servidor lo pide, más de un worker de ingesta.

### O6. (Media) SQLite como BD del agente no aguanta varios usuarios

- **Por código:** el agente puede correr en SQLite (default de la app de escritorio) o Postgres. En SQLite, un turno mantiene **una transacción abierta mientras el LLM responde**, y las escrituras internas compiten con ese lock; el propio código documenta que un `BEGIN IMMEDIATE` global lo convirtió en un fallo garantizado de 30 s por turno.
- **Consecuencia:** correcto para un usuario local; **inadecuado para SAVI Servidor**. El pool Postgres del agente es 10 + 5 = 15 conexiones, razonable, pero hay que usarlo, no SQLite.
- **Corrección:** exigir Postgres en el modo servidor y revisar el patrón de la transacción larga por turno.

### O7. (Baja) Reuso de refresh token no invalida la familia

- **Por código:** la rotación funciona (se revoca el `jti` viejo y se emite uno nuevo). Pero si llega un refresh **ya revocado** (token robado y reusado), simplemente falla; no revoca toda la cadena del usuario ni alerta.
- **Corrección:** ante un refresh revocado, `revoke_all_for_user` y registrar el evento.

### Timeouts y límites que **sí** están bien

| Control | Estado |
|---|---|
| `statement_timeout` del ERP | 60 s por consulta (verificado: `pg_sleep` se corta ahí). |
| Solo lectura del ERP | Forzado a nivel de conexión, resiste intentos de desactivarlo. |
| EXPLAIN gate del SQL libre | Rechaza consultas que el planner estima en > 1.000 filas. |
| Tamaño de subida | 20 MB por archivo, 500 páginas, 50.000 fragmentos totales. |
| Mensaje de chat | 16.000 caracteres; respuesta 20.000. |
| Cierre ordenado | `timeout_graceful_shutdown` para no colgar al salir. |
| Piso de login fallido | 250 ms, equipara los caminos (verificado en frío). |
| Sin fuga en error 500 | No hay handler catch-all; Starlette responde texto plano sin traza. |

## Qué está bien (verificado)

| Área | Detalle |
|---|---|
| Arquitectura | Módulos con dominio, aplicación e infraestructura consistentes; puertos claros (`Embedder`, `LLMRunner`, repositorios). |
| Conversaciones | Todas las rutas validan el dueño (`expected_owner`) con usuario **y** base. |
| `consultar_datos` | Identificadores de una lista cerrada del catálogo y valores como bind params: sin inyección SQL. |
| Solo lectura en el ERP | `default_transaction_read_only` resiste los intentos con `set_config` (verificado). |
| Login | Piso de tiempo contra enumeración de clientes; el refresh vuelve a leer el usuario del ERP (un usuario desactivado no renueva). |
| Cifrado | Credenciales con Fernet y rotación de clave; exportación con PBKDF2 y contraseña mínima de 8 caracteres. |
| Frontend | Markdown con `html: false` y DOMPurify; mermaid en modo `strict`; links con `noopener`. |
| Documentos de la empresa | Permisos aplicados antes de buscar; descarga protegida con `nosniff` (verificado en fases anteriores). |
| UX del chat | Moderna y cuidada, con sugerencias por módulo y responsive en móvil. |
| Calidad | 432 tests, Ruff y Pyright strict en verde; RNF de importación medidos. |

## Plan de corrección

El plan detallado, con una spec por frente de trabajo, está en
[`docs/seguridad/00-plan.md`](seguridad/00-plan.md). Resumen del orden:

1. **Ya (horas):**
   - C1 (`tools=[]` más test);
   - M2 (secreto por defecto);
   - M3 (actualizar dependencias);
   - O3 (`/health` sin tocar la BD).
2. **Antes de usuarios reales (días):**
   - A1 y A2: permisos de datos, lista de funciones y rol sin superusuario, con tests (M4);
   - O1: rate limits en login y chat;
   - O2 y O4: tope de turnos concurrentes y timeout de pared por turno.
3. **Antes de SAVI Servidor:**
   - A3 (alcance del administrador) y M1 (módulos por base);
   - O6 (Postgres obligatorio, no SQLite);
   - O5 (cola de ingesta).
4. **Deuda y pulido:** M5–M9, O7 y las bajas.
