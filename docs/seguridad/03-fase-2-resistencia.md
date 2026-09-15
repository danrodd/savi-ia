# Fase 2 — Resistencia: abuso, concurrencia y timeouts

> Objetivo: que la aplicación aguante uso abusivo y varios usuarios a la vez
> sin degradarse ni disparar costos.
> Esfuerzo estimado: **3 días**. Sin decisiones de producto pendientes.

## Alcance

| # | Hallazgo | Severidad |
|---|---|---|
| O1 | No hay rate limiting en ningún endpoint | Alta |
| O2 | Sin tope de turnos de chat concurrentes | Alta |
| O4 | Un turno de chat no tiene timeout de pared | Media |
| M5 | Turnos concurrentes sobre la misma conversación | Media |

## Principio de diseño de esta fase

Los límites tienen que ser **invisibles para un usuario legítimo** de la app de
escritorio y **efectivos contra un script**. Todos configurables por `.env`,
con defaults holgados, y cada rechazo con un mensaje que explique qué pasó.

---

## O1 — Rate limiting

### Qué está mal

Verificado: 50 logins fallidos en paralelo se procesaron todos. No hay límite
en ningún endpoint. Las contraseñas del ERP son MD5 sin sal.

### Diseño

Middleware propio con ventana deslizante en memoria. **No** `slowapi`: agrega
una dependencia para algo que acá son 60 líneas, y el estado en memoria es
correcto para un proceso único (que es el modelo actual, un solo worker de
uvicorn). Para SAVI Servidor se reemplaza el store, no la lógica.

**Nuevo módulo:** `backend/app/shared/rate_limit/`

```
domain/     → RateLimitPolicy (dataclass), RateLimitExceededError
infrastructure/ → InMemorySlidingWindow, RateLimitMiddleware
```

### Políticas

| Ámbito | Clave | Límite por defecto | Respuesta al superarlo |
|---|---|---|---|
| `POST /auth/login` | IP + login normalizado | 10 por minuto, 30 por hora | 429 con `Retry-After` |
| `POST /auth/login` fallidos consecutivos | mismo login | 5 seguidos → bloqueo 15 min | 429, sin decir si el usuario existe |
| `POST /auth/refresh` | IP | 30 por minuto | 429 |
| `POST /chat` | usuario | 20 por minuto, 200 por hora | 429 con `errorCode: rate_limited` |
| Subida de documentos | usuario | 30 por hora | 429 |
| Resto autenticado | usuario | 300 por minuto | 429 |
| `/health`, `/version` | IP | 120 por minuto | 429 |

Todos por `.env`: `RATE_LIMIT_LOGIN_PER_MINUTE`, `RATE_LIMIT_CHAT_PER_MINUTE`, etc.
Un `RATE_LIMIT_ENABLED=false` para desarrollo y para los E2E.

### Detalles que no hay que olvidar

- **La clave del login se normaliza igual que el login** (mayúsculas, `@base`), o se evade cambiando mayúsculas.
- **El bloqueo por fallos consecutivos se limpia con un login exitoso.**
- **`X-Forwarded-For` no se confía** salvo que haya un proxy declarado en configuración; si no, se usa la IP de la conexión. Confiar en el header a ciegas convierte el rate limit en decorativo.
- **El 429 del login no distingue** "usuario bloqueado" de "IP bloqueada": mismo cuerpo.
- El middleware corre **antes** de la autenticación para los endpoints públicos y **después** para los que necesitan el usuario; en la práctica se resuelve con dos capas: por IP en middleware, por usuario en dependencia.

### Criterios de aceptación

- [ ] 11 logins en un minuto desde la misma IP: el 11.º devuelve 429 con `Retry-After`.
- [ ] 5 contraseñas malas seguidas para el mismo login: el 6.º devuelve 429 aunque la contraseña sea correcta, durante 15 minutos.
- [ ] Un login exitoso antes del 5.º fallo resetea el contador.
- [ ] 21 turnos de chat en un minuto: el 21.º devuelve 429 con `errorCode: rate_limited`; el frontend lo muestra como aviso, no como error genérico.
- [ ] Con `RATE_LIMIT_ENABLED=false` nada cambia (para los E2E).

### Tests

| Test | Qué verifica |
|---|---|
| `test_sliding_window_allows_under_limit` / `_blocks_over_limit` | La ventana en sí, sin HTTP. |
| `test_login_rate_limited_by_ip` | 429 tras N intentos. |
| `test_login_lockout_after_consecutive_failures` | Bloqueo por login. |
| `test_successful_login_resets_failure_counter` | No castigar al que se equivocó una vez. |
| `test_chat_rate_limited_per_user` | Límite por usuario, no por IP. |
| `test_rate_limit_disabled_by_setting` | El interruptor funciona. |

### Verificación manual

Repetir la ráfaga de la revisión (`scripts` de carga): 50 logins fallidos en
paralelo. Esperado: los primeros con 401, el resto con 429.

---

## O2 — Tope de turnos de chat concurrentes

### Qué está mal

No hay ningún semáforo. Cada turno con Claude lanza un `claude.exe` propio con
~144.000 tokens de contexto (bajará con C1, pero el proceso sigue). Diez
turnos simultáneos saturan la máquina.

### Cambios

**`backend/app/modules/chat/infrastructure/http/routes.py`** o en el runner
resolutor: un `asyncio.Semaphore` de proceso.

```python
# Un turno = un subproceso del CLI + su contexto. Sin tope, N usuarios
# concurrentes son N procesos y la máquina se queda sin memoria antes de
# que ninguno termine. Se rechaza rápido en lugar de encolar: un chat que
# tarda 3 minutos en arrancar es peor que un "probá de nuevo".
_MAX_CONCURRENT_TURNS = settings.max_concurrent_chat_turns  # default 3
```

- Adquirir **antes** de devolver el `StreamingResponse`, con `acquire` no bloqueante.
- Si no hay lugar: 429 con `errorCode: chat_busy` y un mensaje que diga que hay otras consultas en curso.
- Liberar en un `finally` que cubra también la cancelación del cliente.

**Default 3** para la app de escritorio (un usuario no lo toca nunca) y
configurable por `.env` para servidor.

### Criterios de aceptación

- [ ] Con el default en 1, el segundo turno simultáneo recibe 429 `chat_busy`.
- [ ] Al terminar o cancelarse el primero, el siguiente entra.
- [ ] Cancelar el stream desde el cliente libera el permiso (no se filtra).
- [ ] La escritura del mensaje del asistente, que sobrevive a la cancelación, no queda bloqueada por el semáforo.

### Tests

- `test_second_concurrent_turn_is_rejected`.
- `test_semaphore_released_on_client_cancel` (simula `CancelledError` a mitad del stream).

---

## O4 — Timeout de pared por turno

### Qué está mal

El único límite es `max_agent_turns=40` (rondas de herramienta). Un turno
puede durar indefinidamente reteniendo subproceso, conexión SSE y —con
SQLite— una transacción.

### Cambios

Nuevo `CHAT_TURN_TIMEOUT_S` (default **180**). En `ChatTurnUseCase.execute`,
envolver el consumo del runner con `asyncio.timeout`.

Al vencer:

1. Emitir un `ErrorEvent` con texto claro ("La consulta tardó demasiado y se
   detuvo; probá acotarla").
2. **Persistir lo que se alcanzó a generar** con `finish_reason=INTERRUPTED`,
   igual que hoy hace la cancelación del cliente. Eso ya está resuelto en el
   camino de cancelación: reutilizarlo, no duplicarlo.
3. Cerrar el stream con `done`.

### Criterios de aceptación

- [ ] Un turno que excede el timeout termina con un `error` y luego `done`, no con la conexión colgada.
- [ ] El mensaje parcial queda guardado y visible en el historial.
- [ ] El subproceso del CLI se cierra (verificar que no quedan `claude.exe` huérfanos).

### Tests

- `test_turn_times_out_and_persists_partial` con un runner falso que nunca termina.
- `test_turn_timeout_emits_error_then_done`.

---

## M5 — Un turno por conversación a la vez

### Qué está mal

No hay bloqueo: dos pestañas o un doble envío pueden correr `send`,
`edit_last` o `regenerate` a la vez sobre la misma conversación y dejar ramas
cruzadas (dos mensajes de usuario activos, supersedes pisados).

### Cambios

Bloqueo **por conversación**, no global:

- App de escritorio (SQLite y proceso único): un `dict[UUID, asyncio.Lock]` con limpieza al liberar.
- Para que no se rompa en servidor multiproceso, el candado se encapsula en una interfaz (`ConversationTurnLock`) con implementación en memoria hoy y espacio para una basada en BD (`SELECT … FOR UPDATE` sobre la fila de la conversación) después.

Si el candado está tomado: **409** con `errorCode: conversation_busy`, antes de
abrir el SSE.

### Criterios de aceptación

- [ ] Dos `POST /chat` simultáneos sobre la misma conversación: uno corre, el otro recibe 409.
- [ ] Sobre conversaciones distintas, los dos corren (sujeto al semáforo de O2).
- [ ] El candado se libera ante error y ante cancelación.
- [ ] El frontend muestra el 409 como "ya hay una respuesta en curso" en lugar de un error rojo.

### Tests

- `test_concurrent_turns_same_conversation_conflict`.
- `test_concurrent_turns_different_conversations_allowed`.
- `test_lock_released_on_error`.

---

## Frontend de esta fase

Tres códigos de error nuevos que la interfaz tiene que entender:

| `errorCode` | Situación | Qué muestra |
|---|---|---|
| `rate_limited` | Demasiados pedidos | Aviso con el tiempo de espera, sin perder el texto escrito |
| `chat_busy` | Servidor con turnos al tope | "SAVI está atendiendo otras consultas, probá en un momento" |
| `conversation_busy` | Ya hay un turno en esa conversación | Deshabilitar enviar y avisar |

**Criterio de aceptación:** ninguno de los tres se ve como error genérico ni
pierde el mensaje que el usuario escribió.

---

## Resultado de la fase

- La fuerza bruta contra el login deja de ser viable.
- El costo del chat tiene un techo por usuario.
- La máquina no se satura con turnos concurrentes y ninguno se cuelga para siempre.
- Una conversación no se corrompe por doble envío.

Con la Fase 0, la 1 y la 2 cerradas, SAVI se puede abrir a usuarios reales en
una empresa. Falta la 3 solo si varias empresas comparten instalación.
