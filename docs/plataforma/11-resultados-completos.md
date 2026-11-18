# 11 — Resultados completos: que lo recortado no parezca completo

**Estado:** implementado y probado (2026-11-12, B12–B15 del plan `odd/tasks/hallazgos-primera-demo.md`).
**Origen:** demo con cliente del 2026-11-11.

## 1. Problema

Tres momentos de la demo:

1. **"Me podría regalar la base de datos de los clientes que adquirieron LLANTAS0183"** devolvió 30 clientes: "estos son los primeros 30 [...] El listado continúa con más clientes". El usuario pidió la base y recibió una muestra, sin saber de cuántos.
2. **"Referencias de llantas que no han rotado mucho y tengan cantidades en el inventario"** devolvió 4 referencias. El usuario sabía que la MICHELIN FORCE LTX llevaba tiempo quieta y no salía. SAVI reconoció dos errores:
   - el criterio: tomó "exactamente 1 unidad vendida" y dejó por fuera las de cero ventas, justo las más importantes;
   - el alcance: "la consulta inicial de inventario entregó solo una parte de las referencias".
   Al rehacerlo, solo revisó "las cinco que habían quedado identificadas", no todo el inventario.
3. **El botón Descargar** de las tablas exporta lo que se ve, que es lo que el modelo escribió.

En un sistema de gestión, un listado incompleto que parece completo es peor que un error, porque se usa para decidir.

## 2. Cómo funciona hoy

| Pieza | Límite | Cómo avisa que hay más | Dónde |
|---|---|---|---|
| Catálogo, modo detalle | 30 filas | `truncated` si llegó al tope; al modelo le llega "Se cortó en N filas y hay más". **No dice cuántas hay en total.** | `data_query/domain/semantic_model.py:122`, `run_semantic_query.py:209` |
| Catálogo, modo agregado | 100 filas | Igual. | `semantic_model.py:121` |
| Catálogo: cuándo se considera cortado | `len(rows) >= limit` | Si el resultado tiene exactamente el tope, dice "hay más" aunque no haya más. | `infrastructure/erp_query_executor.py:48` |
| SQL libre (admin) | 50 filas | `truncated` solo si **la estimación del planner** supera el tope. Si el planner estima mal, se corta sin avisar. | `free_query/domain/policy.py:16`, `execute_free_query.py:80` |
| SQL libre: filtro previo (EXPLAIN gate) | estimación de 1.000 filas | Rechaza la consulta completa: "es muy amplia, afina el filtro". | `policy.py:19` |
| SQL libre: forma | sin `WITH`, sin `UNION`, sin `OFFSET`, 2 niveles de subconsulta | Las consultas de análisis (cruzar inventario con ventas de varios periodos) son difíciles de escribir en una sola consulta. | `free_query/application/sql_validator.py` |
| Respuesta del modelo | 20.000 caracteres | Se corta con un aviso. | `settings.py:102`, `chat/infrastructure/llm/truncation.py` |
| Prompt | "hasta ~25 filas, muéstralas todas; si hay más, un top y di el total" | El modelo no siempre conoce el total. | `chat/infrastructure/llm/system_prompt.py:509` |
| Tabla del chat y su descarga | lo que escribió el modelo | La tabla se arma con el Markdown de la respuesta. CSV y Excel exportan ese texto, no los datos de la base. | `frontend/src/modules/chat/components/SaviTable.vue` |

## 3. Causas

1. **El modelo es el que transporta los datos.** Todo lo que el usuario ve y descarga pasó por el texto del modelo. Por eso hay topes chicos, y no por un capricho: cada fila son tokens, cuestan plata y tiempo, y en una tabla de 300 filas el modelo puede saltarse o cambiar un número.
2. **No se informa el total.** El modelo sabe que hay más, pero no cuántos, así que no lo puede decir con precisión ("los primeros 30 de 214").
3. **Los análisis los arma el modelo en su cabeza.** Para la baja rotación pidió el inventario (cortado), pidió ventas por referencia (cortado) y cruzó las dos muestras. El cruce de dos muestras no es el cruce de los datos, y de ahí sale la omisión de la MICHELIN. Además eligió él el criterio.
4. **El SQL libre no ayuda a un análisis completo:** el filtro de 1.000 filas estimadas, la prohibición de `WITH` y el tope de 50 empujan a consultas parciales.

## 4. Diseño propuesto

### 4.1 Separar lo que ve el modelo de lo que recibe el usuario

Cada consulta exitosa al ERP, del catálogo o del SQL libre, genera un **conjunto de resultados** guardado en el servidor:

- **El usuario** ve en el chat una **vista previa** con las primeras filas, que el frontend arma **desde los datos** y no desde el Markdown. Lleva la leyenda "mostrando 30 de 214". La vista del chat se mantiene limitada a propósito, porque una tabla de cientos de filas no se puede leer en una conversación (**decisión del usuario, 2026-11-11**).
- **Exportar:** la tabla tiene el botón **Exportar** con tres formatos, Excel (`.xlsx`), PDF y CSV. El servidor genera el archivo con **todas** las filas del conjunto (hasta el tope, §6) y lo entrega para descargar. El archivo no se arma en el navegador con lo que se ve, sino en el servidor con lo que se consultó.
- **El modelo** recibe el total exacto, una muestra (las primeras 30 filas, como hoy), los totales cuando aplica y el identificador del conjunto. Puede mencionar la tabla ("la tabla completa con los 214 clientes está abajo") sin copiarla.

**Consecuencias:**

- El usuario recibe la base completa aunque el modelo vea 30 filas.
- Los números de la tabla y de la descarga salen de la base, no del modelo: no puede saltarse ni cambiar una fila.
- No sube el costo: las filas no viajan por el modelo.
- **Es la base de P3:** un documento se genera desde el conjunto de resultados, no desde el texto del modelo.

**Seguridad:**

- El conjunto queda atado a la conversación, al usuario y a la base del ERP. El endpoint de descarga exige ser el dueño de la conversación (mismo criterio que las conversaciones hoy).
- Se guarda **la foto del momento**, no la consulta para volver a correrla: lo que se descarga es lo mismo que se conversó, y no se repiten los permisos en un contexto distinto. Con permisos de P1, los campos que el usuario no puede ver nunca entran al conjunto.
- Tiene vencimiento (ver §6) y se borra con la conversación.
- Los conjuntos con datos personales (P1) quedan auditados, incluida cada descarga.

### 4.2 Total exacto y corte honesto

- El catálogo pide `limit + 1` filas para saber si de verdad hay más. Se corrige el falso positivo de `len(rows) >= limit`.
- Si hay más, se cuenta el total con un `COUNT(*)` de la misma consulta sin `LIMIT`, con su propio tiempo máximo. Si el conteo tarda, se informa "más de N".
- El SQL libre hace lo mismo y deja de depender de la estimación del planner para avisar.
- El aviso al modelo pasa de "se cortó y hay más" a "**mostrando 30 de 214; la tabla completa está disponible para el usuario**".

### 4.3 Análisis que se resuelven en la base, no en el modelo

Las preguntas de análisis frecuentes se modelan como entidades del catálogo, para que el cruce sea una sola consulta SQL completa y el criterio sea explícito:

| Pregunta | Entidad propuesta | Campos clave |
|---|---|---|
| Productos sin movimiento con existencias (la de la MICHELIN) | `inventario_rotacion` | existencia actual, fecha de la última venta, fecha de la última compra, unidades vendidas en el periodo, días sin venta |
| Llantas compradas hace mucho que siguen en bodega | `inventario_rotacion` | fecha de la primera y de la última compra con existencia |
| Clientes que compraron una referencia | `ventas_detalle` con los campos del tercero (P1) | — |
| Clientes que dejaron de comprar | `terceros` con la última compra (P1, §5.2) | fecha del último movimiento |

- "Baja rotación" deja de ser un criterio que inventa el modelo: es un filtro explícito ("días sin venta > 365") y el resultado lo dice.
- La lista de entidades se valida con las preguntas reales de la demo y de las baterías existentes (`backend/scripts/bateria_*`).

### 4.4 SQL libre para análisis (solo administradores)

- Se permite `WITH` sin recursión y sin escritura. El motivo original de prohibirlo ("el `LIMIT` global se evade con CTE") deja de aplicar, porque el tope lo pone ahora el conjunto de resultados al leer.
- El filtro previo de 1.000 filas estimadas pasa a medir el **costo** que estima el planner, junto con el `statement_timeout` de 60 s que ya existe. Lo que se protege es la carga sobre el ERP, no la cantidad de filas, que ahora no viajan por el modelo.

### 4.5 Lo que dice el modelo

- El prompt pide decir siempre cuántas filas hay y si la tabla está completa.
- Pide no armar análisis cruzando muestras: si el resultado está cortado, usar un agregado o la entidad de análisis.
- La leyenda de la tabla ("214 filas · Descargar Excel") la pone el frontend con los datos. No depende de que el modelo se acuerde.

## 5. Criterios de aceptación

1. "Clientes que compraron LLANTAS0183": el chat muestra la vista previa con "mostrando 30 de N", y **Exportar** entrega un Excel, un PDF o un CSV con los N clientes. El modelo dice el total exacto.
2. "Productos sin ventas en el último año con existencias": la MICHELIN FORCE LTX aparece, junto con todas las demás que cumplen. El criterio queda dicho en la respuesta.
3. La tabla y la descarga coinciden fila por fila con la base (test de integración contra la base de pruebas).
4. Un resultado de exactamente 30 filas no dice "hay más".
5. Otro usuario, aunque tenga el identificador del conjunto, no puede descargarlo (403 o 404).
6. Un conjunto vencido o de una conversación borrada ya no se descarga.
7. El costo en tokens de "la base de clientes" no crece con la cantidad de filas.
8. Paridad entre Claude, OpenAI y Gemini en los criterios 1 y 2.

## 6. Decisiones (2026-11-11)

1. **Vista del chat:** limitada a una vista previa; lo completo va por **Exportar** en Excel, PDF o CSV (decisión del usuario).
2. **Tope de filas de un conjunto exportable:** 10.000, con la leyenda "primeras 10.000 de N". Un número mayor se vuelve un problema para la carga del ERP y para generar el PDF. Se mantiene la propuesta mientras el usuario no pida otra cosa.
3. **Cuánto tiempo se guarda un conjunto:** lo mismo que la conversación, con un máximo de 90 días. Se mantiene la propuesta.
4. **Cuántas filas ve el modelo:** siguen siendo 30 (o 100 en agregados), más el total y los totales por columna. Se mantiene la propuesta.

5. **Cómo se pide la exportación:** de las dos formas, con el mismo generador (decisión del usuario).
   - **Botón Exportar** en cada tabla: es el camino principal, no gasta tokens y no depende del modelo.
   - **Por el chat** ("pásemelo en Excel"): el modelo llama a la exportación con la referencia del conjunto y el formato, y el archivo aparece como adjunto descargable en la respuesta. El modelo nunca escribe el contenido del archivo.
   - SAVI no ofrece exportar en cada tabla. Lo menciona solo cuando la tabla está recortada ("le muestro 30 de 214; puede exportar la lista completa").
   - La herramienta de exportación entra por el patrón dispatcher, para respetar el máximo de 4 herramientas del MCP; se define en P3.

El PDF de una tabla es una exportación de datos. Los documentos con texto, como un informe o una carta con datos, son P3, y reusan este mismo generador.

## 7. Fuera de alcance

- Generar Word o PDF: es P3, que usa estos conjuntos.
- Abrir el catálogo a contabilidad o nómina: está registrado en P1, §5.6.
