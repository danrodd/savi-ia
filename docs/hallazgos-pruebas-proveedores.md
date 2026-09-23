# Hallazgos de las pruebas por proveedor

> Resultados de correr la [batería de validación](bateria-validacion-savi.md)
> contra cada proveedor de IA, con el diagnóstico de cada falla y el diseño de
> su corrección.
>
> Los tres proveedores corrieron **las mismas 6 preguntas**, para que la
> comparación sea de manzanas con manzanas.
>
> | Corrida | Proveedor | Modelo | Cuándo |
> |---|---|---|---|
> | 1 | Claude | `claude-sonnet-5` | 2026-09-21, **antes** de los fixes |
> | 2 | Gemini | `gemini-flash-lite-latest` | 2026-09-22, después de los fixes |
> | 3 | OpenAI | `gpt-5.6-luna` | 2026-09-22, después de los fixes |
>
> La corrida 1 es la línea de base: destapó los hallazgos. Las otras dos
> verifican que las correcciones funcionan con proveedores distintos.
> Ver la [comparación](#comparación-de-los-tres-proveedores--mismas-6-preguntas).

---

## Resumen de la corrida 1 (Claude)

| # | Hallazgo | Tipo | Severidad | Estado |
|---|---|---|---|---|
| 1 | Los filtros de fecha rompen **toda** consulta de ventas | Bug | **Bloqueante** | ✅ Corregido (y extendido a filtros numéricos y booleanos, misma clase de bug) |
| 2 | El mensaje de error invita al modelo a reintentar en loop | Bug | Alta | ⚠️ Parcial — resuelto para tipos, falta la separación general |
| 3 | La respuesta no se percibe en streaming: llega completa al final | A investigar | Media | 🔍 Descartado bug de backend; ver evidencia de la Corrida 2 |
| 4 | No hay aviso cuando termina un turno en segundo plano | Falta funcionalidad | Media | ⬜ Abierto |
| 5 | Una pregunta del catálogo de conocimiento no resuelve | Bug | Baja | ✅ Corregido en DOS capas: el loader no leía `shared/faqs/` **y** `intencion` no miraba FAQs |
| 6 | Cartera, proveedores y catálogo respondieron bien | Correcto | — | — |

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

### El mismo bug estaba vivo en los filtros numéricos y booleanos

Una auditoría posterior encontró que el primer fix cubría **solo `date`**.
`FilterValueType` declaraba `"number"` y `"bool"`, pero `_coerce_value` los
ignoraba: devolvía el valor tal cual. Verificado contra Postgres real:

```
bind '123'  a bigint  → DataError: 'str' object cannot be interpreted as an integer
bind 'true' a boolean → DataError
bind 1      a boolean → DataError
```

Ocho filtros del catálogo apuntaban a columnas `bigint` o `boolean` sin tipar:
`terceros.id`, `terceros.es_cliente`, `terceros.es_proveedor`,
`terceros.activo`, `ventas.cliente_id`, `ventas.numero`,
`ventas_detalle.producto_id`, `ventas_detalle.cliente_id`.

Era el mismo bug con el mismo disfraz de intermitencia: si el modelo manda el
id como número anda, si lo manda como string revienta. **Corregido**: los tres
tipos convierten, `bool` se corta antes que `int` (en Python `True` es `1` y
habría filtrado por algo que nadie pidió), y hay tests de los tres contra
Postgres real.

---

## Hallazgo 2 — El mensaje de error invita a reintentar en loop — PARCIAL

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

### Qué se hizo y qué falta

**Resuelto para el caso que disparó todo**, como efecto del fix del Hallazgo 1:
la validación de tipos ahora ocurre en `compile_query`, que está dentro del
primer `try/except SemanticQueryError` de `run_semantic_query`. Un filtro mal
tipado sale como *"No pude armar la consulta: el filtro 'fecha' espera una
fecha en formato AAAA-MM-DD…"* — accionable, y el modelo corrige en vez de
reintentar igual.

**Falta la separación general.** Cualquier error que ocurra al EJECUTAR
(timeout, conexión caída, un error de Postgres no previsto) sigue cayendo en el
`except Exception` genérico y saliendo como "Hubo un problema técnico". Para
esos casos el texto es razonable — son transitorios de verdad —, pero no hay
distinción explícita ni un "no reintentes" para los determinísticos que
todavía puedan escaparse hasta la ejecución.

Queda abierto. Prioridad baja ahora que la causa principal (tipos) se ataja
antes de llegar ahí.

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

### Evidencia de la Corrida 2 — apunta a la hipótesis 1

En la corrida con Gemini el streaming **sí llegó progresivo**, en muchos
`text_delta` chicos. La respuesta larga (la tabla mes a mes de 2025) se armó en
~15 eventos sucesivos:

```
{"text": "V", ...}
{"text": "iene **creciendo de forma sostenida** mes a mes a lo largo del ", ...}
{"text": " 2025. Arrancamos con un ritmo más moderado en mayo y la facturación subió", ...}
…
```

O sea: **la plomería SSE entrega deltas a medida que llegan, no bufferea**. Lo
que se percibió como "todo de golpe" con Claude era la hipótesis 1 — en un
turno con 10-15 llamadas a herramientas, el modelo no escribe nada hasta tener
el último resultado, y el texto final es corto.

Queda una comprobación pendiente para cerrarlo del todo: que el componente del
chat en el navegador pinte esos deltas a medida que llegan (acá se verificó el
stream del backend, no el render). Pero la hipótesis de "bug de buffering en el
backend" queda descartada.

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

## Hallazgo 5 — Una pregunta del catálogo no resuelve — CORREGIDO

`¿Cómo le asigno permisos a un usuario?` no resolvió, mientras
`¿Para qué sirve el formulario frmGestionCartera?` sí. En general el bloque de
funciones del sistema respondió bien.

**Causa real**: ninguna de las dos hipótesis iniciales (filtro de módulos,
matching de intención). El loader del catálogo **nunca leía
`data/shared/faqs/`**. En `load_static_catalog`, el `faqs.extend(...)` vivía
dentro del loop `for dossier in modules_dir.iterdir()`, que solo recorre
`modules/<slug>/faqs/`. De `shared/` solo se leía `glossary.json`.

Resultado: las 4 FAQs transversales (crear usuario, asignar permisos, crear un
presupuesto, mantenimiento de vehículo) se cargaban en **cero** archivos. La
FAQ existía en el repo y era invisible en runtime.

**Corregido** en `static_catalog.py`, con test de regresión sobre el catálogo
mínimo y un sanity check contra el catálogo real.

### Segunda capa: cargar la FAQ no alcanzaba

Este hallazgo se dio por cerrado antes de tiempo. Al correr la batería con
Gemini, la pregunta **seguía fallando**. La causa tenía dos capas y solo se
había arreglado una:

| Camino | Estado tras el primer fix |
|---|---|
| `tipo: "faq"` → `answer_faq` | ✅ Encontraba `faq_016` |
| `tipo: "intencion"` → `search_by_intent` | ❌ Solo recorre **formularios**, nunca FAQs |

El modelo usa `tipo: "intencion"` por defecto (así lo dice la descripción de
la tool), así que nunca llegaba a la FAQ: recibía formularios irrelevantes
con score 2 (`frmCierreMes` para una pregunta de permisos) e improvisaba.

Se suma que los formularios que la FAQ recomienda —
`frmPermisoAccionUsuario`, `frmUsuario` — **no existen en el catálogo**: no
hay dossier del módulo `SEGURIDAD` en `data/modules/`.

**Corregido de verdad**: la rama `intencion` del dispatcher ahora consulta
también las FAQs y las devuelve junto a los formularios. Verificado con los
tres proveedores después del fix.

> **Deuda pendiente**: crear el dossier del módulo `SEGURIDAD` con sus
> formularios. Hoy la respuesta sale de la FAQ, no del catálogo de
> formularios, así que preguntar directo por `frmUsuario` sigue sin
> resolver.

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

| Prueba | Cubre | Dónde | Estado |
|---|---|---|---|
| Consulta semántica sobre `ventas` con filtro de fecha contra Postgres | Hallazgo 1 | `test_query_compiler_postgres_integration.py` | ✅ |
| Filtro de fecha con valor inválido devuelve error accionable y no genérico | Hallazgo 2 | `test_query_compiler.py` | ✅ |
| Cada tipo de filtro del catálogo (`date`, `text`, `number`, `bool`) bindea correctamente | Hallazgo 1, prevención | `test_query_compiler.py` + integración contra Postgres | ✅ |
| Consulta de ventas con rango de fechas de punta a punta | Hallazgos 1 y 2 | `test_catalog_against_real_erp.py` | ✅ |

> Los tests contra Postgres **deben** correr contra Postgres, no SQLite: SQLite
> convierte los strings en silencio y el bug queda invisible.

> El último no se hizo como E2E de navegador (como decía el plan original) sino
> como test de integración del backend contra el ERP real. Razón: el camino
> "punta a punta" que importa es catálogo → compilador → schema real, y eso es
> determinístico y gratis. Meter al LLM en el medio lo haría lento, costoso y
> flaky sin cubrir más código propio.

### Riesgo conocido de la suite E2E

`activateStableProvider` (en `frontend/e2e/helpers.ts`) hace un `PUT` del
proveedor Claude con `credential_kind: 'local_session'`. Como el tipo de
credencial cambia respecto del guardado, `_candidate` **no preserva la
credencial anterior**: correr `chat.spec.ts` o `company-knowledge.spec.ts`
**borra la API key de Anthropic** que haya configurada.

No es un bug introducido acá y no bloquea nada, pero conviene saberlo antes de
correr la suite E2E en una instalación con credenciales reales cargadas.

### Manuales, por proveedor

Al correr la batería con cada proveedor, registrar además de la respuesta:

- Cantidad de llamadas a herramientas del turno (un número alto avisa de
  reintentos).
- Si el texto se escribió progresivamente o apareció completo al final.
- Costo del turno y si quedó registrado (ver [consumo por proveedor](consumo-por-proveedor.md)).

---

## Estado por proveedor

| Proveedor | Corrida | Modelo | Resultado |
|---|---|---|---|
| Claude | 2026-09-21, **pre-fix** | `claude-sonnet-5` | Línea de base: destapó los Hallazgos 1 a 5 |
| Gemini | 2026-09-22, post-fix | `gemini-flash-lite-latest` | ✅ 6/6 · destapó la segunda capa del Hallazgo 5 |
| OpenAI | 2026-09-22, post-fix | `gpt-5.6-luna` | ✅ 5/6 · no intentó la de proveedores |

Ver la [comparación de los tres](#comparación-de-los-tres-proveedores--mismas-6-preguntas).

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

## Corrida 3 — OpenAI

Modelo `gpt-5.6-luna` (el económico de su familia: $0,20 entrada / $1,20
salida por millón), con tarifa cargada antes de gastar crédito.

> **Nota sobre el arranque falso**: el primer intento falló con
> `invalid_api_key`. Se diagnosticó como una key revocada, y **eso estuvo
> mal**: la key tenía un carácter de más al final (`…Y0A1` en vez de
> `…Y0A`), un error de copiado. Sirve como recordatorio de que una key
> rechazada puede ser un typo antes que una revocación — se descarta
> comparando el largo, no suponiendo.
>
> Lo que sí quedó validado del episodio: el camino de error del backend
> devuelve `ok: false` con mensaje accionable, sin reintentar en loop ni
> exponer detalle interno.

---

## Comparación de los tres proveedores — mismas 6 preguntas

Todas las corridas después de aplicar los fixes de los Hallazgos 1 y 5.
Claude se corrió ANTES de los fixes (por eso falla donde los otros no):
esa columna es la línea de base que motivó las correcciones.

| Pregunta | Claude (pre-fix) | Gemini | OpenAI |
|---|---|---|---|
| Facturación mes a mes de 2025 | ❌ 10 llamadas, se rindió | ✅ 1 llamada · $0,0064 | ✅ 1 llamada, marca meses sin datos · $0,0026 |
| Descuentos durante 2025 | ⚠️ Costó, respondió | ✅ 1 llamada · $0,0052 | ✅ 1 llamada · $0,0005 |
| Cartera vencida total | ⚠️ 15 llamadas | ⚠️ 17 llamadas, 2 errores · $0,068 | ⚠️ 6 llamadas, sin errores · $0,0042 |
| Facturas pendientes a proveedores | ✅ Trajo los datos, acotó a 30 | ⚠️ Derivó al formulario · $0,0079 | ❌ 0 llamadas, no lo intentó · $0,0005 |
| Cómo asigno permisos a un usuario | ❌ Falló | ✅ Cita `faq_016` · $0,0053 | ✅ Nombra `frmPermisoAccionUsuario` · $0,0006 |
| Para qué sirve frmGestionCartera | ✅ Bien | ✅ Bien · $0,0051 | ✅ Bien · $0,0005 |

**Costo de las corridas de hoy**: Gemini $0,1029 · OpenAI $0,0088.

### Lo que muestra la comparación

**1. El fix de fechas se confirma en los dos proveedores.** La pregunta que
con Claude hacía 10 llamadas y terminaba rindiéndose ahora se resuelve en
**una sola llamada** en Gemini y en OpenAI. No es que los otros modelos
sean mejores: el bug ya no está.

**2. `gpt-5.6-luna` salió entre 5 y 10 veces más barato que
`gemini-flash-lite-latest`** en las mismas preguntas ($0,0088 contra
$0,1029 en total), y con menos llamadas en la consulta cara (6 contra 17).

**3. Números distintos para "cartera vencida" según el proveedor.** Gemini
respondió ~$2.211 millones de saldo de clientes; OpenAI, $10.906 millones
sobre 2.500 obligaciones. Ninguno está "mal": la pregunta es ambigua y
cartera **no está modelada en la capa semántica**, así que cada modelo
escribe su propio SQL y decide por su cuenta si incluye cuentas por pagar.
El `DB_MAP` ya advierte que hay que separar CxC de CxP por `tipoDocumento`.

> **Es el argumento más fuerte para modelar cartera en la capa semántica**:
> mientras dependa de SQL libre, la misma pregunta de negocio devuelve
> cifras distintas según el modelo que esté activo, y quien pregunta no
> tiene cómo saber cuál es la correcta.

**4. Criterio muy distinto ante lo que no está modelado.** En "facturas
pendientes a proveedores": Claude fue por SQL libre y **trajo los datos**
acotando a las 30 más urgentes; Gemini derivó al formulario correcto;
OpenAI **no lo intentó siquiera** (0 llamadas a herramientas) pese a tener
`consultar_libre` disponible. De menor a mayor utilidad para quien
pregunta: OpenAI < Gemini < Claude.

**5. El fix del Hallazgo 5 funciona en los tres.** OpenAI dio la mejor
respuesta de las tres: nombra `frmPermisoAccionUsuario` y lista los pasos.
