# Batería — Conocimiento de la empresa: ciclo de vida y fallos

> Parte de: [Conocimiento de la empresa](00-prd.md). Complementa la
> [batería de lectura con IA](bateria-lectura-ia.md) y la de
> [permisos y bases](bateria-permisos-bases.md).
> Fecha: 2026-09-23. Script: `backend/scripts/bateria_ciclo_vida.py`.
> Proveedor: OpenAI, `gpt-6-luna` (chat y lectura).

## Resultado

| Bloque | Resultado | Qué prueba |
|---|---|---|
| **Reemplazar** | **5/5** | La versión nueva responde con el dato nuevo, en conversaciones nuevas y abiertas, y se vuelve a leer con IA |
| **Borrar** | **5/5** | Deja de responder y de citarse en el acto, también en una conversación abierta |
| **Cambiar el alcance** | **7/7** | Quitar un módulo o una base oculta el documento en la siguiente pregunta; cambiar el título cambia la cita |
| **Listado** | **2/2** | "¿Qué documentos hay?" trae todos los que el usuario puede ver y ninguno más |
| **Fallos del proveedor** | **5/5** | Con un modelo de lectura inexistente el documento no se traba, avisa el motivo y "Leer con IA" lo recupera |
| **Archivos difíciles** | **5/5** | PDF con contraseña, PDF cortado, imagen renombrada y archivo vacío; la cola sigue |

**29/29** en las dos corridas con todas las correcciones. Las dos primeras
corridas dieron 27/29 y 28/29 y así aparecieron los defectos de §3 (y un
error del propio script en S05, que preguntaba un dato que ya había salido
en la conversación).

La batería encontró **cuatro defectos reales** (§3), todos corregidos con un
test que falla sin la corrección. Uno de ellos, el 404 al mandar el primer
mensaje de una conversación recién creada, **no era de esta funcionalidad**:
afectaba a cualquier cliente rápido, incluido el frontend.

Costo por corrida: ~US$0,01 de preguntas + la lectura con IA de 6 páginas.

## 1. Cómo se prueba

Documentos sintéticos (escaneos, sin capa de texto) con datos inventados,
subidos con el prefijo `[QA ciclo]`. El script borra los de corridas
anteriores al empezar. Usuarios de QA de la
[batería de permisos](bateria-permisos-bases.md#1-usuarios).

Cada escenario pregunta **antes y después** del cambio. En las
conversaciones que ya estaban abiertas se pregunta un dato que **todavía no
salió** en esa conversación: si se preguntara el mismo, el modelo podría
repetirlo del historial, que el usuario ya vio, y eso no es una fuga.

## 2. Escenarios y resultado (corrida final)

### Reemplazar (`Política de viáticos`: v1 85.000 → v2 120.000)

| # | Paso | Resultado |
|---|---|---|
| R01 | Subir la v1 | Lista, leída con IA (1 página) |
| R02 | QAINV pregunta el viático | "$85.000" [D1] |
| R03 | Reemplazar por la v2 | Lista, versión 2, **leída otra vez con IA** (no reutiliza la lectura de la v1) |
| R04 | Conversación nueva | "$120.000" [D1]; no menciona 85.000 |
| R05 | Conversación abierta, dato nuevo (hospedaje) | "$230.000 por noche" [D1]; no menciona 190.000 de la v1 |

### Borrar (`Reglamento de parqueadero`)

| # | Paso | Resultado |
|---|---|---|
| B01 | Antes de borrar | "14 cupos para motos" [D1] |
| B02 | Borrar | 204 |
| B03 | Conversación abierta, dato nuevo (multa) | "No encontré el valor de esa multa"; sin cita |
| B04 | Conversación nueva | No lo encuentra; sin cita (ver §4.1) |
| B05 | Borrar otra vez | 204 (idempotente) |

### Cambiar el alcance (`Procedimiento de inventario cíclico`)

| # | Paso | Resultado |
|---|---|---|
| S01 | Visible para todos: QACXC pregunta | "40 referencias cada semana" [D1] |
| S02 | Se limita al módulo INVENTARIO. QACXC, misma conversación, dato nuevo | "No encontré la tolerancia"; sin cita |
| S03 | QACXC, conversación nueva | No lo encuentra |
| S04 | QAINV (tiene INVENTARIO) | "0,8 %" [D1] |
| S05 | Se limita a la base Sur Andina. QAINV en FRAMI, conversación abierta, dato nuevo | No lo encuentra |
| S06 | QAINV en Sur Andina | "El auditor de inventarios" [D1] |
| S07 | Se cambia el título | Cita el título nuevo, no el viejo |

### Listado

| # | Usuario y base | Ve | No ve |
|---|---|---|---|
| L01 | QAINV en FRAMI | Los 11 documentos a los que tiene acceso: devoluciones, descuentos FRAMI, viáticos y el corpus público | Acta de junta, cartera, descuentos Sur Andina, el reglamento borrado |
| L02 | QACXC en Farmacias ("listame las políticas") | Cartera y viáticos | Devoluciones, acta, políticas de otras bases, el procedimiento de inventario |

### Fallos del proveedor

| # | Paso | Resultado |
|---|---|---|
| F01 | Configurar `modelo-inexistente-qa` como modelo de lectura | Se guarda (no se valida al guardar) |
| F02 | Subir un escaneo | Termina en segundos: `no_text`, código `ai_failed`, "No se pudo leer con IA: el proveedor activo no respondió. Revisá su configuración y el modelo de lectura, y después usá «Leer con IA»." |
| F03 | Restaurar el modelo | El script lo restaura en un `finally`, aunque algo falle |
| F04 | "Leer con IA" | Listo, leído con IA |
| F05 | Preguntar | "45 minutos por vehículo" [D1] |

### Archivos difíciles

| # | Archivo | Resultado |
|---|---|---|
| A01 | PDF con contraseña | `failed` · "El PDF está cifrado y requiere contraseña." |
| A02 | PDF cortado a la mitad | `failed` · "No pudimos leer el PDF." |
| A03 | PNG con extensión `.pdf` | 415 al subir: tipo no soportado |
| A04 | Archivo vacío | 422 al subir: "El archivo está vacío." |
| A05 | Un PDF normal después de todos | Listo: la cola no se trabó |

## 3. Defectos encontrados y corregidos

### 3.1 Primer mensaje de una conversación nueva: 404 intermitente

**No era de esta funcionalidad y afectaba al frontend.** `POST
/conversations` respondía 201 **antes** de confirmar la transacción: FastAPI
cierra por defecto las dependencias con `yield` después de mandar la
respuesta. Un cliente que manda el primer mensaje enseguida podía llegar
antes que el commit y recibir 404. En la batería pasó con 7 ms de
diferencia.

Corregido: `AgentSessionDep` usa `Depends(..., scope="function")`, que
confirma antes de responder. Solo `conversations` y `usage` usan esa
sesión y ninguno hace streaming (el chat usa sesiones cortas propias).
Test: el commit ocurre antes que la respuesta.

### 3.2 Proveedor caído: el aviso sugería justo lo que iba a fallar

Con la IA sin responder, un escaneo quedaba en "El PDF parece escaneado.
Podés leerlo con IA", y volver a intentarlo fallaba igual hasta corregir el
proveedor. Ahora, si hubo páginas que se mandaron a la IA y todas cayeron
al respaldo, el documento queda con el código `ai_failed` y un aviso que
apunta al proveedor.

### 3.3 Un archivo vacío se aceptaba

Quedaba como "parece escaneado". Ahora subir o reemplazar con un archivo
vacío devuelve 422.

### 3.4 El límite de tokens por minuto de OpenAI no se reintentaba

Al repetir C08 nueve veces seguidas, algunos turnos terminaban en "No pude
generar una respuesta" sin costo. El log (que ahora guarda la excepción)
mostró la causa: **el límite de 200.000 tokens por minuto de la cuenta**.
OpenAI lo manda como evento `error` dentro del stream (`APIError` con
`code="rate_limit_exceeded"` y sin estado HTTP), no como un 429, y el runner
solo reintentaba 429 y 5xx. Con varios usuarios a la vez pasaría lo mismo en
producción.

Corregido: antes del primer token se reintentan, con la espera de siempre,
el límite por minuto dentro del stream y los cortes de conexión o timeouts
(`APIConnectionError`). El saldo agotado (`insufficient_quota`) sigue sin
reintentarse. Con la corrección, 9 repeticiones seguidas terminaron sin
ningún turno caído.

## 4. Observaciones

### 4.1 B04: a veces responde como si el tema fuera ajeno

Tras borrar el reglamento, una corrida respondió a "¿cuántos cupos de motos
hay en el parqueadero?" con "Solo puedo ayudarte con temas del producto y
de tu empresa". No filtra nada, pero el tono es de pregunta fuera de tema
cuando lo correcto es "no encontré eso en los documentos". En la otra
corrida respondió "No encontré información sobre los cupos". Queda
registrado; no se ajustó el prompt por un caso aislado.

### 4.2 Preguntas mixtas: consulta el ERP, pero a veces lo dice mal

Con la indicación nueva en la respuesta de documentos (ver
[permisos, §5.1](bateria-permisos-bases.md#51-preguntas-que-mezclan-erp-y-documentos)),
C08 consultó el ERP en 23 de 25 respuestas. En 4 de ellas, aun habiendo
consultado, respondió "no puedo confirmar si hay existencias" en vez de
"no encontré Potabon K en el inventario". No inventa, pero la frase es más
floja de lo que el dato permite.

### 4.3 Lo que ya se probaba solo con tests unitarios

Timeout del proveedor, reintentos con espera, saldo agotado y respuestas
sin alguna página tienen tests unitarios con un lector falso
(`test_pdf_ai_reading.py`). Esta batería cubre de punta a punta el caso
más común: el proveedor configurado no responde.

## 5. Cómo volver a correrla

Con el backend en `localhost:8000`, la lectura con IA activada y, antes,
la [batería de permisos](bateria-permisos-bases.md) (el listado espera ver
sus documentos):

```powershell
cd backend
uv run python scripts/bateria_ciclo_vida.py                     # todo
uv run python scripts/bateria_ciclo_vida.py --solo fallos       # un bloque
```
