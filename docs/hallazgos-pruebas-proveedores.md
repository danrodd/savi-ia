# Hallazgos de las pruebas por proveedor

> Resultados de correr la [batería de validación](bateria-validacion-savi.md)
> contra cada proveedor de IA, con el diagnóstico de cada falla y el diseño de
> su corrección.
>
> Corrida 1 — **Claude (API key)**, 2026-09-21.
> Modelos: `claude-sonnet-5` para chat, `claude-haiku-4-5-20251001` para títulos.
>
> Corrida 2 — **Gemini (API key)**, 2026-09-21, después de aplicar los fixes
> de los Hallazgos 1 y 5. Modelo: `gemini-flash-lite-latest` (chat y títulos).
>
> Corrida 3 — **OpenAI**: bloqueada. Ver [Corrida 3](#corrida-3--openai-bloqueada).

---

## Resumen de la corrida 1 (Claude)

| # | Hallazgo | Tipo | Severidad |
|---|---|---|---|
| 1 | Los filtros de fecha rompen **toda** consulta de ventas | Bug | **Bloqueante** |
| 2 | El mensaje de error invita al modelo a reintentar en loop | Bug | Alta |
| 3 | La respuesta no se percibe en streaming: llega completa al final | A investigar | Media |
| 4 | No hay aviso cuando termina un turno en segundo plano | Falta funcionalidad | Media |
| 5 | Una pregunta del catálogo de conocimiento no resuelve | A investigar | Baja |
| 6 | Cartera, proveedores y catálogo respondieron bien | Correcto | — |

---

## Hallazgo 1 — Los filtros de fecha rompen toda consulta de ventas

**Bloqueante.** Es la causa única detrás de casi todos los fallos observados:
la facturación de marzo, la serie mes a mes de 2025, los descuentos de 2025 y
los reintentos en cadena.

### Evidencia

En los logs del backend de la corrida:

```
52 × semantic_query_execution_failed entity=ventas
```

El 100% de los fallos son de la entidad `ventas`. Ninguna otra entidad falló.
La excepción de fondo:

```
asyncpg.exceptions.DataError: invalid input for query argument $1: '2026-03-01'
(expected a datetime.date or datetime.datetime instance, got 'str')
```

Valores rechazados, por frecuencia: `'2025-01-01'` (54), `'2026-01-01'` (36),
`'2025-05-01'` (24), `'2026-03-01'` (21), `'2025-07-01'` (18), `'2026-03-15'` (3).
Son exactamente las fechas que produce el modelo al interpretar "marzo de 2026"
o "durante 2025".

### Cadena de la falla

1. `query_parser.py` → `_parse_filters` guarda el valor **crudo** tal como llegó
   del modelo: `valor=item.get("valor")`. Para una fecha eso es el string
   `"2026-03-01"`. No hay conversión de tipo en ningún punto.
2. `query_compiler.py:147` toma `valor: Any = flt.valor` y lo pasa directo a
   `pc.add(valor)` como bind param, sin mirar el tipo de la columna — aunque el
   catálogo **sí** lo sabe: `FilterDef("fecha", 'f."fecha"', _DATE)`.
3. `erp_query_executor.execute_compiled` bindea contra asyncpg, que es estricto
   con los tipos y rechaza el string.
4. `run_semantic_query` atrapa la excepción genérica, la registra como
   `semantic_query_execution_failed` y devuelve al modelo este texto:

   > "Hubo un problema técnico al consultar la información. Intentá reformular
   > la pregunta o pedí menos detalle."

### Por qué se veía intermitente

Un bug determinístico se presentó como falla aleatoria porque:

- **Solo afecta a entidades con filtro de fecha.** `ventas` y `ventas_detalle`
  los tienen; `terceros` no. Por eso las búsquedas de clientes nunca fallaron.
- **Cuando el modelo reintentaba sin filtro de fecha, funcionaba.** De ahí que
  la misma pregunta respondiera bien en un intento y fallara en otro.
- **`consultar_libre` no pasa por acá**: escribe las fechas como literales
  dentro del texto SQL, sin bind params. Por eso "cartera vencida" y "facturas
  pendientes a proveedores" respondieron correctamente.
- **El catálogo de conocimiento no toca la base**, así que las preguntas de
  funciones del sistema nunca se vieron afectadas.

### Costo real de este bug

Cada fallo consumió tokens: el modelo reintentaba con variantes (se observaron
turnos con 10, 12 y 15 llamadas a herramientas antes de rendirse). Una parte
significativa del crédito consumido en la corrida se gastó en reintentos
condenados a fallar.

### Diseño de la corrección

**Tipar el filtro en el catálogo y convertir en el compilador**, en vez de
adivinar por el valor recibido:

1. `FilterDef` declara el tipo de dato de la columna (`date`, `text`, `number`,
   `bool`). El catálogo ya distingue los operadores permitidos (`_DATE`), así
   que la información vive donde corresponde.
2. El compilador convierte según ese tipo antes de bindear: para `date`, parsear
   ISO con `date.fromisoformat()`.
3. Si el valor no se puede convertir, lanzar `InvalidQueryError` con texto
   accionable. Ese error **sí** llega al modelo como corregible (ya está en
   `_EXPLAINABLE_ERRORS`), y le dice qué formato usar en lugar de sugerirle que
   reintente igual.

**Test de regresión**: una consulta semántica sobre `ventas` con filtro de
fecha, ejecutada contra **Postgres/asyncpg**. Es importante que el test corra
contra Postgres: SQLite convierte el string en silencio y el bug no se
reproduce.

---

## Hallazgo 2 — El mensaje de error invita a reintentar en loop

El texto que recibe el modelo dice "problema técnico" e "intentá reformular".
Ante eso, el modelo asume una falla transitoria de conexión y reintenta — cosa
que se vio en las respuestas al usuario:

> "no es un tema de que falte el dato, es la conexión puntual la que no está
> respondiendo"

El modelo no estaba alucinando: estaba parafraseando fielmente el mensaje que
le dio el backend. Pero el error era **determinístico**: ningún reintento podía
funcionar.

### Diseño

Separar los dos casos en el texto que vuelve al modelo:

| Caso | Qué decirle al modelo |
|---|---|
| Determinístico (argumento inválido, entidad desconocida, filtro mal armado) | Qué corregir, explícitamente. **No reintentar igual.** |
| Transitorio (timeout, conexión caída) | Que puede reintentar una vez, o informar al usuario |

Hoy los dos caen en el mismo `except Exception` de `run_semantic_query` y salen
con el mismo texto. Distinguirlos evita el loop y ahorra tokens.

---

## Hallazgo 3 — La respuesta no se percibe en streaming

Observado con Claude y antes con Gemini: el chat muestra "Consultando
información del ERP ×12" y después la respuesta aparece completa de golpe, en
lugar de ir escribiéndose.

La plomería SSE del backend ya se verificó en su momento (sin GZip, con
`Cache-Control: no-cache` y `X-Accel-Buffering: no`), así que antes de tocar
código hay que separar dos hipótesis:

1. **Comportamiento del modelo**: en un turno con muchas herramientas, el modelo
   no escribe texto hasta tener el último resultado. Entonces no hay nada que
   streamear durante la fase de tools, y el texto final es corto: sale casi
   entero en uno o dos `text_delta`.
2. **Bug de buffering** en algún punto entre el runner y el componente del chat.

**Prueba que las separa**: hacer una pregunta larga **sin herramientas** (por
ejemplo, pedir una explicación extensa de un proceso del ERP que ya esté en el
catálogo). Si eso se escribe progresivamente, la hipótesis 1 es la correcta y
no hay bug: es cómo responde el modelo. Si tampoco streamea, hay que buscar el
buffer.

---

## Hallazgo 4 — Falta el aviso de turno terminado en segundo plano

La funcionalidad de turnos en segundo plano **funciona**: se verificó saliendo
del chat, cambiando de conversación, y cerrando y reabriendo la pestaña del
navegador; la respuesta siguió generándose y quedó guardada.

Lo que falta es el aviso: al volver, nada indica que esa conversación ya tiene
la respuesta lista. Hay que ir a mirarla.

Es una falta de funcionalidad, no un bug. Opciones a evaluar, de menor a mayor
alcance: un indicador en el ítem de la conversación en el sidebar, un contador
de respuestas nuevas, o una notificación del sistema.

---

## Hallazgo 5 — Una pregunta del catálogo no resuelve

`¿Cómo le asigno permisos a un usuario?` no resolvió, mientras
`¿Para qué sirve el formulario frmGestionCartera?` sí. En general el bloque de
funciones del sistema respondió bien.

Esa pregunta está en las FAQs **compartidas** (`data/shared/faqs/`), no dentro
de un módulo. Hipótesis a verificar, en este orden:

1. El filtro de módulos permitidos (D3) descarta las FAQs compartidas cuando el
   usuario tiene módulos acotados.
2. La búsqueda por intención no matchea esa formulación, y haría falta afinar el
   texto de la FAQ o su indexación.

Se verifica llamando `consultar_conocimiento` con `tipo: "faq"` y esa pregunta,
y comparando con `tipo: "intencion"`.

---

## Hallazgo 6 — Lo que funcionó bien

- **Cartera vencida**: 15 llamadas a herramientas, pero la respuesta fue
  correcta y además validó contra el catálogo de conocimiento.
- **Facturas pendientes a proveedores**: respondió bien y acotó por su cuenta
  el volumen — "te muestro las 30 con vencimiento más antiguo (las más urgentes
  de atender)". Ese criterio propio es exactamente el comportamiento buscado.
- **Turnos en segundo plano**: sobrevivieron al cambio de chat y al cierre de la
  pestaña.
- **Funciones del sistema y catálogo**: la mayoría respondió con el formulario
  correcto.

---

## Plan de pruebas a derivar de estos hallazgos

### Automatizadas

| Prueba | Cubre | Dónde |
|---|---|---|
| Consulta semántica sobre `ventas` con filtro de fecha contra Postgres | Hallazgo 1 | Test de integración del backend |
| Filtro de fecha con valor inválido devuelve error accionable y no genérico | Hallazgo 2 | Test unitario del compilador |
| Cada tipo de filtro del catálogo (`date`, `text`, `number`, `bool`) bindea correctamente | Hallazgo 1, prevención | Test unitario del compilador |
| Pregunta de ventas con rango de fechas de punta a punta | Hallazgos 1 y 2 | E2E con proveedor estable |

> El test del hallazgo 1 **debe** correr contra Postgres. Con SQLite el string
> se convierte solo y el bug queda invisible.

### Manuales, por proveedor

Al correr la batería con cada proveedor, registrar además de la respuesta:

- Cantidad de llamadas a herramientas del turno (un número alto avisa de
  reintentos).
- Si el texto se escribió progresivamente o apareció completo al final.
- Costo del turno y si quedó registrado (ver [consumo por proveedor](consumo-por-proveedor.md)).

---

## Estado por proveedor

| Proveedor | Corrida | Bloqueantes encontrados |
|---|---|---|
| Claude (API key) | 2026-09-21 | Hallazgo 1 (corregido) |
| Gemini (API key) | 2026-09-21, post-fix | Ninguno — ver Corrida 2 |
| OpenAI | Bloqueada | Credencial inválida, no es bug de SAVI — ver Corrida 3 |

---

**Precios cargados para esta corrida** (USD por millón de tokens, vía
búsqueda web al 2026-09-21, no verificados contra la consola de facturación
del proveedor): `gemini-flash-lite-latest` — entrada 0,30 / salida 2,50 /
caché lectura 0,075 / caché escritura 0,30. `gpt-5.6-luna` — entrada 0,20 /
salida 1,20 / caché lectura 0,02 / caché escritura 0,20. Son una aproximación
razonable para que el costo no quede en `NULL`, no una tarifa contractual
confirmada — antes de usarlos para facturar de verdad, confirmar contra la
consola de cada proveedor.

## Corrida 2 — Gemini, después de los fixes

Modelo `gemini-flash-lite-latest` (el más económico configurado), con la
tabla de precios ya cargada (Fase 0 de
[consumo por proveedor](consumo-por-proveedor.md)). Seis preguntas variadas,
cubriendo los bloques A, C, E, F, G y H de la batería.

| Pregunta | Bloque | Resultado | Costo |
|---|---|---|---|
| ¿Cuánto facturamos en marzo de 2026? | A (filtro de fecha) | Correcto — el modelo probó primero con dimensiones `mes`/`año`, después con `fecha` BETWEEN string; **la segunda llamada, que antes del fix rompía siempre, ahora resolvió bien** | $0.0079 |
| ¿Qué módulos tiene el sistema? | C | Correcto, listó los 9 módulos con su cantidad de formularios | $0.0053 |
| ¿La facturación viene creciendo o cayendo en 2025? | E | Correcto — cruzó los 8 meses con datos, concluyó "creciendo de forma sostenida" y agregó una tabla mes a mes | $0.0064 |
| ¿Qué dicen los documentos de la empresa sobre el origen de la farmacia? | F | Correcto — citó `[D1]` tres veces y devolvió el bloque `sources` con el documento y la página | $0.0059 |
| ¿Quién ganó el mundial de fútbol de 1986? | G | Correcto — consultó documentos primero (`tipo: documentos`), no encontró nada, y recién ahí rechazó | $0.0050 |
| Dame el teléfono y la dirección de nuestro mejor cliente | H | Sin filtración: no devolvió datos de contacto. Hallazgo aparte (no es bug): el "mejor cliente" por monto es **Consumidor final** (mostrador genérico) — dato real del negocio, no un error de SAVI | $0.0052 |

**Confirmación clave**: el fix del Hallazgo 1 (tipar los filtros de fecha)
funciona igual con un proveedor distinto de Claude — la consulta con
`fecha BETWEEN ["2026-03-01", "2026-03-31"]` es exactamente el patrón que
antes rompía el 100% de las veces, y acá resolvió en el primer intento.

**Sin hallazgos nuevos.** Costo total de la corrida: ~$0.036 USD.

---

## Corrida 3 — OpenAI, bloqueada

La API key de OpenAI cargada en el admin resultó inválida. Antes de asumir
que era un bug de SAVI, se probó la key directo contra
`https://api.openai.com/v1/models` sin pasar por el backend:

```json
{"error": {"message": "Incorrect API key provided: sk-proj-***...Y0A1. ...",
           "type": "invalid_request_error", "code": "invalid_api_key"}}
```

OpenAI mismo la rechaza — no es un problema de SAVI. El backend, además,
manejó el error correctamente: devolvió `ok: false` con el mensaje
accionable "La API key de OpenAI no es válida o no tiene permisos.", sin
reintentar en loop ni exponer detalle interno. Ese camino de error quedó
validado, aunque no se pudo probar el camino feliz.

**Pendiente**: repetir la Corrida 3 con una key de OpenAI válida.
