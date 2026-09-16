# La respuesta no se corta al salir del chat

> Fecha: 2026-09-15 · Estado: **implementado**.
> Pedido: que al salir de la conversación la respuesta siga generándose y esté
> completa al volver, como en Claude, ChatGPT o Gemini.

## Qué pasa hoy (medido)

El turno vive atado a la conexión HTTP. Si el cliente se va, el generador del
SSE se cancela y **la generación muere con él**.

Prueba contra el backend real: se pidió una respuesta larga y se cortó la
conexión al primer fragmento.

```
conexión cortada a los 9,7 s con 70 caracteres
a los  5 s: 70 caracteres, finish_reason=interrupted
a los 15 s: 70 caracteres, finish_reason=interrupted
a los 60 s: 70 caracteres, finish_reason=interrupted
```

Se guarda lo poco que alcanzó a generar y ahí queda. El usuario vuelve y
encuentra media frase.

Que el mensaje **se guarde** ya funciona (los writers tienen su propia sesión
y sobreviven a la cancelación). Lo que no sobrevive es la **generación**.

## Qué se quiere

| Situación | Hoy | Objetivo |
|---|---|---|
| Cambio de conversación a mitad de respuesta | Se corta | Sigue; al volver está completa |
| Cierro la pestaña y vuelvo en 30 s | Se corta | Sigue; al volver **se ve escribiendo en vivo** |
| Recargo la página | Se corta | Se reengancha al turno en curso |
| Aprieto "Detener" | Se corta | Se corta (explícito) |
| Otro dispositivo abre la misma conversación | — | Ve la respuesta en curso |

## Diseño

La idea entera es una línea: **el turno deja de ser el stream y pasa a ser una
tarea; el stream se suscribe a ella.**

```
POST /chat  ──▶  registro de turnos  ──▶  tarea del turno (vive sola)
                        │                        │
                        │                        ├── acumula eventos en un buffer
                        │                        └── al terminar, persiste (como hoy)
                        ▼
                  SSE suscripto  ──▶  cliente
                  (si se va, la tarea NO se entera)
```

### Registro de turnos (en memoria, por proceso)

```python
class RunningTurn:
    conversation_id: UUID
    events: list[ChatEvent]      # todo lo emitido, en orden
    done: bool
    task: asyncio.Task[None]
```

- **Un turno por conversación.** El registro *es* el candado que hoy hace
  `concurrency.py`: si hay turno para esa conversación, `409 conversation_busy`.
- **Cupo global**: se toma al crear la tarea y se suelta en su `finally`, no al
  cerrar la conexión. Hoy está atado a la conexión y con esto se filtraría.
- **Timeout de pared**: pasa a la tarea. Hoy envuelve el generador del SSE.
- **Retención**: el turno terminado queda unos minutos para que quien vuelve
  enseguida vea el final en vivo; después se descarta. El mensaje ya está en la
  base, así que perder el buffer no pierde nada.

En memoria y por proceso, como el índice de documentos y el worker de ingesta.
**En modo servidor multiproceso esto no alcanza**: haría falta un bus
compartido o afinidad de sesión. Queda anotado, no resuelto.

### Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| `POST` | `/chat` | Igual que hoy, pero arranca la tarea y se suscribe |
| `GET` | `/chat/activo?conversation_id=` | ¿Hay turno en curso? Lo usa la interfaz al abrir |
| `GET` | `/chat/stream?conversation_id=` | Reengancha: reenvía lo emitido y sigue en vivo |
| `POST` | `/chat/detener` | Corta el turno de verdad |

**El reenganche reenvía desde el evento 0**, sin cursor. El mensaje se
reconstruye entero a partir de la lista de eventos, que es idempotente: mucho
más simple que sincronizar posiciones, y el buffer de un turno es de pocos KB.

### "Detener" tiene que dejar de ser decorativo

Hoy el botón hace `abortController.abort()`: corta el fetch y con eso la
generación. Cuando la generación deje de depender de la conexión, **abortar el
fetch dejaría de detener nada**. Por eso el endpoint explícito: sin él, el
cambio convierte un botón que funciona en uno que miente.

### Frontend

1. Al abrir una conversación, preguntar por `/chat/activo`.
2. Si hay turno, abrir `/chat/stream` y pintar desde el evento 0.
3. "Detener" llama a `/chat/detener` y después corta el stream local.
4. Al cambiar de conversación, solo se cierra el stream: la tarea sigue.

## Criterios de aceptación

Entre paréntesis, con qué se verificó cada uno.

- [x] Cortar la conexión a los 2 s de una respuesta larga: el mensaje guardado queda **completo** (medido, abajo).
- [x] Recargar la página a mitad de respuesta: la interfaz se reengancha y se ve terminar en vivo (E2E `recargar a mitad de respuesta…`).
- [x] Cambiar de conversación y volver: la respuesta está completa (medido con `GET /chat/stream`, abajo).
- [x] "Detener" corta de verdad: el mensaje queda `interrupted` y no crece (medido, abajo).
- [x] Dos `POST /chat` sobre la misma conversación: el segundo recibe 409 (`test_same_conversation_twice_is_busy`).
- [x] El cupo global se libera aunque el cliente se haya ido (`test_the_turn_survives_the_subscriber`, `test_slot_is_released_when_the_task_ends`).
- [x] El timeout de pared sigue aplicando al turno (`test_timeout_applies_to_the_task`).
- [x] `activo`, `stream` y `detener` devuelven 404 sobre una conversación ajena (`test_background_turn_endpoints.py`).
- [x] Salir de la conversación no marca la respuesta como interrumpida; volver se reengancha (`backgroundTurn.spec.ts`).

## Medido después del cambio

Mismo procedimiento que la medición de arriba, contra el backend real.

**Cortar la conexión a los 2 s** (antes: 70 caracteres congelados en
`interrupted`):

```
conexion cortada a los 2.0s con 0 caracteres
justo despues: /chat/activo -> {'activo': True}
a los  15s: sin mensaje todavia            | activo=True
a los  45s: sin mensaje todavia            | activo=True
a los  75s: 5431 caracteres, complete      | activo=False
a los 165s: 5431 caracteres, complete      | activo=False
```

**Reenganche** — se corta a los 2 s y 20 s después se pide `/chat/stream`:

```
GET /chat/stream -> 200
reenganchado a los 47.4s: 4069 caracteres, done=complete
guardado: 4069 caracteres
```

**Detener**, con texto ya generado:

```
POST /chat/detener -> 204
a los  5s: 5580 caracteres, interrupted | activo=False
a los 45s: 5580 caracteres, interrupted | activo=False  <- no crecio
```

## Vale para los cuatro proveedores

El cambio vive **por encima** del adaptador: el registro envuelve
`ChatTurnUseCase.execute()`, y ahí es donde también estaba (y sigue estando) la
persistencia del parcial al cancelar. Debajo, `ResolvingLLMRunner` elige entre
`ClaudeAgentRunner`, `GeminiRunner` y `OpenAIRunner`. Ninguno de los tres toca
la cancelación: no hay un solo `except CancelledError` en los runners.

Claude local y Claude por API key son **el mismo runner**: `credential_kind`
solo cambia las variables de entorno que recibe el subproceso del CLI
(`build_claude_env`).

| Proveedor | Estado | Verificado |
|---|---|---|
| Claude `local_session` | activo | Medición + E2E de recarga |
| Claude `api_key` | mismo runner | Por construcción (solo cambia el env) |
| Gemini `api_key` | configurado | Medición (abajo) |
| OpenAI `api_key` | **sin credencial** | No probado: no hay clave en este equipo |

Medición con Gemini activo, mismo procedimiento:

```
conexion cortada a los 2.0s con 0 caracteres
justo despues: /chat/activo -> {'activo': True}
a los 10s: sin mensaje todavia          | activo=True
a los 25s: 5757 caracteres, complete    | activo=False
a los 70s: 5757 caracteres, complete    | activo=False
```

Que Gemini funcione es la prueba que más pesa: su adaptador es streaming HTTP,
no un subproceso, así que si el mecanismo dependiera del transporte se habría
notado acá. OpenAI comparte esa forma y el mismo caso de uso, pero **queda sin
medir** hasta que haya una clave.

## La URL tenía que moverse antes

Un defecto que solo apareció al probar el reload: `ChatView` navegaba a
`/c/:id` recién **después** de terminar el turno (`await store.sendMessage()` y
después `router.replace`). Durante toda la respuesta la URL seguía siendo `/`,
así que un F5 a mitad de la primera respuesta de una conversación nueva no
tenía a qué reengancharse: perdía la conversación entera.

Ahora la navegación la dispara un `watch` sobre `activeConversationId`, en
cuanto la conversación existe.

## Dos trampas que aparecieron al implementarlo

Las dos filtraban el cupo global, que es la peor forma de fallar: a los tres
usos nadie puede chatear y no hay ningún error que lo explique.

**1. El `finally` no corre si la tarea nunca arrancó.** `Detener` apretado en el
primer segundo cancela una tarea que todavía no se ejecutó: la corrutina no
empieza, así que su `try/finally` tampoco. El turno quedaba marcado como en
curso para siempre. El cierre se movió a `add_done_callback`, que corre igual.

**2. Un `await` dentro de una tarea cancelada no se ejecuta.** Liberar el cupo
pasaba por `async with self._guard`, y en una tarea cancelada ese `await`
vuelve a lanzar `CancelledError` antes de decrementar. El candado se sacó
entero: el bloque que reserva no tiene ni un `await`, así que en asyncio ya es
atómico sin ayuda.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Un turno huérfano consume CPU y dinero si nadie lo mira | El timeout de pared y `max_agent_turns` siguen aplicando |
| El buffer crece sin control | `max_response_chars` ya acota el texto; los turnos terminados se descartan por TTL |
| Reenganche duplicando texto | Se reconstruye el mensaje desde cero con la lista completa de eventos |
| Multiproceso | No soportado; documentado. El modo servidor ya asume un worker |
