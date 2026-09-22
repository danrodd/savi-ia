# Hallazgos de las pruebas por proveedor

> Resultados de correr la [batería de validación](bateria-validacion-savi.md)
> contra cada proveedor de IA, con el diagnóstico de cada falla y el diseño de
> su corrección.
>
> Corrida 1 — **Claude (API key)**, 2026-09-21.
> Modelos: `claude-sonnet-5` para chat, `claude-haiku-4-5-20251001` para títulos.

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
| Claude (API key) | 2026-09-21 | Hallazgo 1 |
| Gemini | Pendiente | — |
| OpenAI | Pendiente | — |

> Antes de correr Gemini y OpenAI: cargar la tabla de precios de sus modelos, o
> el consumo de esas corridas se guarda sin costo. Ver
> [consumo por proveedor](consumo-por-proveedor.md), Fase 0.
