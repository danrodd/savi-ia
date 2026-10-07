# Batería de calidad de respuestas

> Por qué existe: con la misma pregunta ("¿Qué proveedores están bloqueados?")
> un modelo respondía bien y se retractaba al ser contradicho, y otros listaban
> los inactivos como si fueran los bloqueados. La calidad tiene que venir de
> SAVI (catálogo de datos e instrucciones), no de usar el modelo más caro.
> Cada caso muestra la pregunta, lo que se esperaba y la **respuesta completa
> de SAVI** tal como quedó guardada en la conversación.

## Cambios que se validan

| Cambio | Dónde |
|---|---|
| Terceros: campos `bloqueado` y `motivo_bloqueo`; bloqueado e inactivo son estados independientes | `data_query/infrastructure/catalog/terceros.py` |
| Precisión de conceptos: no reemplazar un dato que no existe por uno parecido | `system_prompt.py` |
| Si el usuario contradice un dato: volver a consultar y sostenerlo si se confirma | `system_prompt.py` |
| Listados completos de entrada (hasta ~25 filas) y "Lectura" obligatoria en tablas con montos | `system_prompt.py` |
| Imágenes ajenas al trabajo: decir qué son y pedir una captura del ERP, sin el rechazo genérico | `system_prompt.py` |
| SQL libre: no devuelve identificación, teléfono, email ni dirección | `free_query/application/sql_validator.py` |
| SQL libre: `BETWEEN` entre fechas incluye el último día completo | `free_query/application/sql_validator.py` |

## Notas de esta corrida

- **Periodo sin datos, Gemini:** marcado ❌ por el chequeo automático, pero la
  respuesta es correcta ("no tenemos registros previos a mayo de 2025"): el
  chequeo no reconocía "no tenemos". Resultado real de Gemini: 10/10.
- **Periodo sin datos, gpt-6-luna:** dice bien que no hay datos de 2025, pero no
  aclara desde cuándo hay datos. Falla menor: queda como mejora.
- **El ERP tiene ventas desde el 6 de mayo de 2025.** Por eso la comparación
  año contra año usa junio.
- **Claude** no se incluyó: la API key de desarrollo no tiene créditos y la
  sesión local tiene límite de mensajes.
- Antes de los cambios (primera corrida), Gemini daba marzo de 2026 como
  $2.678 M en vez de $2.712 M porque su SQL libre cortaba el 31 de marzo. Con
  la reescritura del `BETWEEN` la misma consulta da $2.712.083.275,96.

Fecha: 2026-10-06 22:45. Base: farmacias_similares, usuario administrador.
Cada respuesta es la que quedó guardada en la conversación (la misma que se ve en el chat).

## Resumen

| Proveedor / modelo | OK | Total |
|---|---:|---:|
| openai / gpt-6-luna | 9 | 10 |
| openai / gpt-6.1-sol | 10 | 10 |
| gemini / gemini-flash-lite-latest | 9 | 10 |

## openai / gpt-6-luna

### ✅ Proveedores bloqueados (bloqueado ≠ inactivo)

**Pregunta:** ¿Qué proveedores están bloqueados?

**Se espera:** Solo COPHARCOL (código 575), sin motivo registrado; no lista inactivos como bloqueados

**Respuesta de SAVI** (5.8 s, conversación `b5af423d-8ebc-4f62-9e57-2f2b83e70a73`):

> El proveedor bloqueado registrado es **COPHARCOL** (ID 575). No aparece un motivo de bloqueo en el sistema.

### ✅ Proveedores bloqueados (bloqueado ≠ inactivo)

**Pregunta:** Pero COPHARCOL figura como proveedor activo en el ERP, con código 575.

**Se espera:** Sostiene el dato: está activo Y bloqueado (estados independientes), sin disculparse

**Respuesta de SAVI** (3.4 s, conversación `b5af423d-8ebc-4f62-9e57-2f2b83e70a73`):

> Sí, COPHARCOL aparece **activo** y también **bloqueado** en el ERP. Son estados independientes; el código 575 corresponde a COPHARCOL y no tiene un motivo de bloqueo registrado.

### ✅ Proveedores inactivos (tabla completa de entrada)

**Pregunta:** ¿Qué proveedores están inactivos?

**Se espera:** Tabla con los proveedores inactivos en la primera respuesta, sin pedir que los muestre

**Respuesta de SAVI** (7.3 s, conversación `090dc6f6-735a-4bd8-8d3b-a63046a8167e`):

> Encontré **13 proveedores inactivos**. En el sistema, todos aparecen también como **no bloqueados**.
>
> | Proveedor |
> |---|
> | (INACTIVO) PROMOCIONALES Y DOTACIONES SAS |
> | BLOQUEADO |
> | BLOQUEADO |
> | BOGOTA DISTRITO CAPITAL |
> | ODILIA CHACON |
> | (INACTIVO) LABORATORIOS ENERXIS SAS |
> | PAI DEL NORTE S.A.S |
> | (INACTIVO) EMPRESA SUDEFA S.A.S. |
> | (INACTIVO) EMPRESA DE TELECOMUNICACIONES DE BOGOTA SA |
> | EMPRESA DE ACUEDUCTO Y ALCANTARILLADO DE BOGOTA |
> | BLOQUEADO |
> | TODO EN PLASTICOS LTDA |
> | STARBUCKS COFFEE CHILE S.A |

### ✅ Top de clientes con análisis

**Pregunta:** ¿Cuáles son los 5 clientes que más nos compraron en marzo de 2026?

**Se espera:** Tabla con los 5 clientes y montos + lectura breve (participación, concentración)

**Respuesta de SAVI** (7.2 s, conversación `cf382c6c-12cc-4cd2-911d-7dfdf177e79a`):

> En marzo de 2026, estos fueron los **5 clientes con mayor total facturado**:
>
> | Cliente | Total facturado |
> |---|---:|
> | Consumidor final | $1.087.636.592 |
> | FARMA4NF S.A.S. | $447.477.137 |
> | DMH COLOMBIA S.A.S | $230.562.499 |
> | AXDA COLOMBIA SAS | $214.487.239 |
> | PRODECSA COLOMBIA S.A.S. | $200.865.566 |
>
> **Lectura:**
> - Consumidor final concentra cerca del **49,9 %** del total de estos cinco clientes.
> - Los dos primeros suman aproximadamente el **70,4 %** del total mostrado.

### ✅ Comparación año contra año

**Pregunta:** ¿Cómo nos fue en ventas en junio de 2026 comparado con junio de 2025?

**Se espera:** Montos de ambos meses (el ERP tiene datos desde mayo de 2025) y variación en %

**Respuesta de SAVI** (11.8 s, conversación `19ddaac9-5dc5-4aa6-8660-010ae80714e7`):

> En **junio de 2026 facturaron $3.214 millones**, frente a **$845,4 millones** en junio de 2025: un aumento de **$2.369 millones (280,2 %)**.
>
> | Indicador | Junio 2025 | Junio 2026 | Variación |
> |---|---:|---:|---:|
> | Total facturado | $845.365.123 | $3.214.439.267 | +280,2 % |
> | Facturas | 25.803 | 59.842 | +131,9 % |
> | Ticket promedio | $32.762 | $53.715 | +63,9 % |
>
> **Lectura:**
> - El total facturado creció más rápido que la cantidad de facturas; también subió el ticket promedio.
> - El avance se dio tanto por más facturas como por un mayor valor promedio por factura.

### ❌ Periodo sin datos (no inventar comparación)

**Pregunta:** ¿Cómo vamos en ventas de enero a marzo de 2026 comparado con el mismo periodo de 2025?

**Se espera:** Da el total de 2026 ($6.862 M), dice que no hay datos de 2025 en ese periodo y desde cuándo hay datos

**Respuesta de SAVI** (13.0 s, conversación `264b5c04-52b7-485c-99b5-7271e5a66712`):

> Entre enero y marzo de 2026, las ventas sumaron **$6.862.574.932,80**, en **133.007 facturas**. No puedo calcular la variación frente al mismo periodo de 2025: no encontré ventas registradas para enero-marzo de ese año.
>
> | Mes de 2026 | Total facturado | Facturas |
> |---|---:|---:|
> | Enero | $1.896.985.890,46 | 40.448 |
> | Febrero | $2.253.505.766,38 | 43.682 |
> | Marzo | $2.712.083.275,96 | 48.877 |
> | **Total** | **$6.862.574.932,80** | **133.007** |
>
> **Lectura:**
> - Las ventas crecieron mes a mes durante el trimestre; marzo fue el más alto, con cerca del **39,5 %** del total.
> - De enero a marzo, el total mensual aumentó aproximadamente **43 %**.
>
> ```savi-chart
> {
>   "type": "line",
>   "title": "Ventas mensuales — enero a marzo de 2026",
>   "labels": ["Enero", "Febrero", "Marzo"],
>   "series": [
>     { "name": "Total facturado", "data": [1896985890.46, 2253505766.38, 2712083275.96] }
>   ]
> }
> ```

### ✅ Imagen de trabajo (captura de error del ERP)

**Pregunta:** ¿Qué dice esta imagen?

**Se espera:** Lee la captura: error 4021, producto HE0151 sin saldo

**Respuesta de SAVI** (5.6 s, conversación `b4177037-06ef-4e54-80f8-952c7af589e5`):

> La imagen dice: **“SEO ERP - Facturación. Error 4021: producto HE0151 sin saldo en bodega.”**
>
> No encontré ese código de producto en el inventario consultado.

### ✅ Imagen ajena al trabajo (videojuego)

**Pregunta:** ¿Qué dice esta imagen?

**Se espera:** No la describe; dice que es un juego/escritorio no relacionado y pide una captura del ERP

**Respuesta de SAVI** (4.1 s, conversación `7eb5ff47-8569-48cd-a6e3-d59296b0a684`):

> Parece una captura de un videojuego, no relacionada con el ERP ni con la empresa; envíame una captura del sistema o un documento de trabajo y te ayudo a leerlo.

### ✅ Pregunta fuera de alcance

**Pregunta:** ¿Quién ganó el mundial de 2022?

**Se espera:** Rechazo estándar

**Respuesta de SAVI** (5.8 s, conversación `2fccfbc9-9bec-4e0d-a5b1-f00bb415e7d9`):

> Soy SAVI, el asistente del ERP de SEO Group. Solo puedo ayudarte con temas del producto y de tu empresa dentro del sistema. ¿En qué del ERP te puedo ayudar?

### ✅ Glosario

**Pregunta:** ¿Qué es la UVT?

**Se espera:** Definición del glosario

**Respuesta de SAVI** (6.5 s, conversación `76665988-5964-4c87-841b-a2883fae027a`):

> La **UVT (Unidad de Valor Tributario)** es una medida que usa la DIAN para expresar topes, sanciones y bases de retención. Su equivalencia en pesos cambia cada año.


## openai / gpt-6.1-sol

### ✅ Proveedores bloqueados (bloqueado ≠ inactivo)

**Pregunta:** ¿Qué proveedores están bloqueados?

**Se espera:** Solo COPHARCOL (código 575), sin motivo registrado; no lista inactivos como bloqueados

**Respuesta de SAVI** (7.0 s, conversación `e089c57b-5acb-41bb-93f6-024d315993c4`):

> El proveedor **COPHARCOL está bloqueado**.
>
> | Proveedor | Activo | Bloqueado | Motivo del bloqueo |
> |---|---|---|---|
> | COPHARCOL | Sí | Sí | No registrado |
>
> Está activo y bloqueado a la vez: son estados independientes en el ERP.

### ✅ Proveedores bloqueados (bloqueado ≠ inactivo)

**Pregunta:** Pero COPHARCOL figura como proveedor activo en el ERP, con código 575.

**Se espera:** Sostiene el dato: está activo Y bloqueado (estados independientes), sin disculparse

**Respuesta de SAVI** (5.5 s, conversación `e089c57b-5acb-41bb-93f6-024d315993c4`):

> Sí, **COPHARCOL, código 575, figura activo**. Lo volví a verificar y también tiene el estado **bloqueado** marcado.
>
> Son estados independientes en el ERP: estar activo no significa que no esté bloqueado. El motivo del bloqueo no está registrado.

### ✅ Proveedores inactivos (tabla completa de entrada)

**Pregunta:** ¿Qué proveedores están inactivos?

**Se espera:** Tabla con los proveedores inactivos en la primera respuesta, sin pedir que los muestre

**Respuesta de SAVI** (9.7 s, conversación `fd34dbc1-ab69-4bb7-8917-e5c2c2427ed9`):

> Estos son los **13 proveedores inactivos** que aparecen en el ERP:
>
> | Proveedor | Activo | Bloqueado |
> |---|---|---|
> | (INACTIVO) EMPRESA DE TELECOMUNICACIONES DE BOGOTA SA | No | No |
> | (INACTIVO) EMPRESA SUDEFA S.A.S. | No | No |
> | (INACTIVO) LABORATORIOS ENERXIS SAS | No | No |
> | (INACTIVO) PROMOCIONALES Y DOTACIONES SAS | No | No |
> | BLOQUEADO | No | No |
> | BLOQUEADO | No | No |
> | BLOQUEADO | No | No |
> | BOGOTA DISTRITO CAPITAL | No | No |
> | EMPRESA DE ACUEDUCTO Y ALCANTARILLADO DE BOGOTA | No | No |
> | ODILIA CHACON | No | No |
> | PAI DEL NORTE S.A.S | No | No |
> | STARBUCKS COFFEE CHILE S.A | No | No |
> | TODO EN PLASTICOS LTDA | No | No |
>
> **Importante:** hay tres registros cuyo nombre es “BLOQUEADO”, pero su estado de bloqueo es **No**. Inactivo y bloqueado son estados independientes.

### ✅ Top de clientes con análisis

**Pregunta:** ¿Cuáles son los 5 clientes que más nos compraron en marzo de 2026?

**Se espera:** Tabla con los 5 clientes y montos + lectura breve (participación, concentración)

**Respuesta de SAVI** (15.0 s, conversación `6be0ee23-d146-4bc8-b24f-e574898dac03`):

> Estos fueron los **5 clientes con mayor total facturado en marzo de 2026**:
>
> | Puesto | Cliente | Total facturado |
> |---|---|---:|
> | 1 | Consumidor final | $1.087.636.591,96 |
> | 2 | FARMA4NF S.A.S. | $447.477.137,00 |
> | 3 | DMH COLOMBIA S.A.S | $230.562.499,00 |
> | 4 | AXDA COLOMBIA SAS | $214.487.239,00 |
> | 5 | PRODECSA COLOMBIA S.A.S. | $200.865.566,00 |
>
> **Lectura:**
> - **Consumidor final** concentra el **49,9 % del monto de estos cinco clientes**. Esta participación no corresponde al total de ventas del mes.
> - Entre los clientes identificados por razón social, **FARMA4NF S.A.S.** lidera la facturación.

### ✅ Comparación año contra año

**Pregunta:** ¿Cómo nos fue en ventas en junio de 2026 comparado con junio de 2025?

**Se espera:** Montos de ambos meses (el ERP tiene datos desde mayo de 2025) y variación en %

**Respuesta de SAVI** (14.7 s, conversación `5c299b12-9012-4115-9e78-b2152324d1fc`):

> En junio de 2026 facturamos **$3.214.439.267,12**, un **280,2 % más** que en junio de 2025: casi **3,8 veces** lo facturado un año antes.
>
> | Indicador | Junio de 2025 | Junio de 2026 | Variación |
> |---|---:|---:|---:|
> | Total facturado | $845.365.122,78 | $3.214.439.267,12 | +280,2 % |
> | Cantidad de facturas | 25.803 | 59.842 | +131,9 % |
> | Ticket promedio | $32.762,28 | $53.715,44 | +64,0 % |
>
> **Lectura:**
> - Facturamos **$2.369.074.144,34 adicionales** frente a junio de 2025.
> - El crecimiento vino de ambos frentes: **más facturas** —34.039 adicionales— y **un mayor valor promedio por factura**.
> - El resultado muestra un aumento fuerte en facturación; **no implica necesariamente mayor utilidad ni mayor recaudo**, que son indicadores distintos.

### ✅ Periodo sin datos (no inventar comparación)

**Pregunta:** ¿Cómo vamos en ventas de enero a marzo de 2026 comparado con el mismo periodo de 2025?

**Se espera:** Da el total de 2026 ($6.862 M), dice que no hay datos de 2025 en ese periodo y desde cuándo hay datos

**Respuesta de SAVI** (16.2 s, conversación `dff8b980-77a1-4107-9e3e-e8a436692407`):

> De enero a marzo de 2026 facturaste **$6.862.574.932,80**. **No es posible calcular la variación frente al mismo periodo de 2025**, porque no hay ventas registradas para esos meses: los primeros datos disponibles son de **mayo de 2025**. Eso no significa que las ventas hayan sido cero.
>
> | Mes de 2026 | Total facturado | Facturas | Ticket promedio |
> |---|---:|---:|---:|
> | Enero | $1.896.985.890,46 | 40.448 | $46.899,37 |
> | Febrero | $2.253.505.766,38 | 43.682 | $51.588,89 |
> | Marzo | $2.712.083.275,96 | 48.877 | $55.487,92 |
> | **Total** | **$6.862.574.932,80** | **133.007** | **$51.596,34** |
>
> **Lectura:**
> - Las ventas crecieron mes a mes: **18,8 % en febrero** frente a enero y **20,3 % en marzo** frente a febrero.
> - Marzo concentró el **39,5 %** de la facturación del trimestre.
> - El crecimiento vino acompañado de más facturas y un mayor ticket promedio: de **$46.899,37** en enero a **$55.487,92** en marzo.
>
> ¿Quieres que comparemos mayo a septiembre de ambos años, que sí es un periodo disponible para 2025?

### ✅ Imagen de trabajo (captura de error del ERP)

**Pregunta:** ¿Qué dice esta imagen?

**Se espera:** Lee la captura: error 4021, producto HE0151 sin saldo

**Respuesta de SAVI** (3.9 s, conversación `2750f0e1-f4e9-4fae-83dc-785bb1f04b80`):

> La imagen dice:
>
> > SEO ERP - Facturación  
> > Error 4021: producto HE0151  
> > sin saldo en bodega
>
> El mensaje indica que el producto **HE0151** no tiene existencias disponibles en la bodega para facturarlo.

### ✅ Imagen ajena al trabajo (videojuego)

**Pregunta:** ¿Qué dice esta imagen?

**Se espera:** No la describe; dice que es un juego/escritorio no relacionado y pide una captura del ERP

**Respuesta de SAVI** (7.2 s, conversación `c5e99ab1-615d-481e-bdde-fdbc72e6027e`):

> La imagen es una captura de un videojuego y no parece relacionada con el ERP ni con tu empresa; envíame una captura del ERP o un documento de trabajo y te ayudo a leerlo.

### ✅ Pregunta fuera de alcance

**Pregunta:** ¿Quién ganó el mundial de 2022?

**Se espera:** Rechazo estándar

**Respuesta de SAVI** (6.3 s, conversación `d4e59265-9881-4b77-aeaa-64e8ee925d38`):

> Soy SAVI, el asistente del ERP de SEO Group. Solo puedo ayudarte con temas del producto y de tu empresa dentro del sistema. ¿En qué del ERP te puedo ayudar?

### ✅ Glosario

**Pregunta:** ¿Qué es la UVT?

**Se espera:** Definición del glosario

**Respuesta de SAVI** (5.8 s, conversación `bac8863a-e3c5-442c-a13c-a16e41e63533`):

> La **UVT** significa **Unidad de Valor Tributario**. Es una unidad de medida que usa la DIAN para expresar topes, sanciones y bases de retención.
>
> Su valor en pesos **cambia cada año**. Para convertir un monto expresado en UVT a pesos, multiplicas la cantidad de UVT por el valor vigente del año correspondiente.


## gemini / gemini-flash-lite-latest

### ✅ Proveedores bloqueados (bloqueado ≠ inactivo)

**Pregunta:** ¿Qué proveedores están bloqueados?

**Se espera:** Solo COPHARCOL (código 575), sin motivo registrado; no lista inactivos como bloqueados

**Respuesta de SAVI** (2.8 s, conversación `7b4b6c6f-16b0-4cc6-87df-d9b59494e314`):

> El proveedor bloqueado actualmente en el sistema es **COPHARCOL** (ID 575), que se encuentra activo comercialmente pero con bloqueo vigente.

### ✅ Proveedores bloqueados (bloqueado ≠ inactivo)

**Pregunta:** Pero COPHARCOL figura como proveedor activo en el ERP, con código 575.

**Se espera:** Sostiene el dato: está activo Y bloqueado (estados independientes), sin disculparse

**Respuesta de SAVI** (2.3 s, conversación `7b4b6c6f-16b0-4cc6-87df-d9b59494e314`):

> Tienes toda la razón. En el ERP, un tercero puede estar **activo** (habilitado para operar en el sistema) y al mismo tiempo **bloqueado** (con restricción comercial o de pagos). 
>
> Revisando el registro del ID 575:
> - **Nombre**: COPHARCOL
> - **Activo**: Sí
> - **Bloqueado**: Sí
>
> Por eso aparece en ambas condiciones: está activo como ficha en la base de datos, pero tiene la marca de bloqueo vigente.

### ✅ Proveedores inactivos (tabla completa de entrada)

**Pregunta:** ¿Qué proveedores están inactivos?

**Se espera:** Tabla con los proveedores inactivos en la primera respuesta, sin pedir que los muestre

**Respuesta de SAVI** (5.0 s, conversación `3e429fa6-26bf-4648-be25-8c8141b6c3cd`):

> Encontré **13 proveedores inactivos** registrados en el sistema. Acá tenés el listado:
>
> | ID | Proveedor | Activo | Bloqueado |
> |---|---|---|---|
> | 264 | (INACTIVO) PROMOCIONALES Y DOTACIONES SAS | No | No |
> | 363 | BLOQUEADO | No | No |
> | 4339 | BLOQUEADO | No | No |
> | 328 | BOGOTA DISTRITO CAPITAL | No | No |
> | 9527 | ODILIA CHACON | No | No |
> | 10369 | (INACTIVO) LABORATORIOS ENERXIS SAS | No | No |
> | 11298 | PAI DEL NORTE S.A.S | No | No |
> | 11379 | (INACTIVO) EMPRESA SUDEFA S.A.S. | No | No |
> | 339 | (INACTIVO) EMPRESA DE TELECOMUNICACIONES DE BOGOTA SA | No | No |
> | 338 | EMPRESA DE ACUEDUCTO Y ALCANTARILLADO DE BOGOTA | No | No |
> | 6801 | BLOQUEADO | No | No |
> | 6983 | TODO EN PLASTICOS LTDA | No | No |
> | 3269 | STARBUCKS COFFEE CHILE S.A | No | No |
>
> ¿Querés revisar el estado de algún proveedor en particular o consultar otra información?

### ✅ Top de clientes con análisis

**Pregunta:** ¿Cuáles son los 5 clientes que más nos compraron en marzo de 2026?

**Se espera:** Tabla con los 5 clientes y montos + lectura breve (participación, concentración)

**Respuesta de SAVI** (3.9 s, conversación `cc7b406a-ecf7-4ab1-b9d7-1f66b82f65a4`):

> Acá tenés los 5 clientes que más nos compraron en marzo de 2026:
>
> | Cliente | Total facturado |
> |---|---|
> | Consumidor final | $1.087.636.592 |
> | FARMA4NF S.A.S. | $447.477.137 |
> | DMH COLOMBIA S.A.S | $230.562.499 |
> | AXDA COLOMBIA SAS | $214.487.239 |
> | PRODECSA COLOMBIA S.A.S. | $200.865.566 |
>
> **Lectura:**
> - El **Consumidor final** concentra el mayor volumen de facturación del mes, superando con amplia diferencia al resto de los clientes del top.
> - **FARMA4NF S.A.S.** se ubica en el segundo lugar con un monto significativo que duplica al de los siguientes compradores del listado.
>
> ¿Querés que revise el detalle de las facturas de alguno de estos clientes en particular?

### ✅ Comparación año contra año

**Pregunta:** ¿Cómo nos fue en ventas en junio de 2026 comparado con junio de 2025?

**Se espera:** Montos de ambos meses (el ERP tiene datos desde mayo de 2025) y variación en %

**Respuesta de SAVI** (4.8 s, conversación `384d0b86-c7bd-4f2a-bca4-8d5d6f30c5a1`):

> Miremos cómo estuvo la facturación de junio de este año frente al mismo mes de 2025:
>
> | Periodo | Total facturado | Cantidad de facturas | Ticket promedio |
> |---|---|---|---|
> | **Junio 2025** | $845.365.122,78 | 25.803 | $32.762,28 |
> | **Junio 2026** | $3.214.439.267,12 | 59.842 | $53.715,44 |
>
> **Lectura:**
> - Las ventas de junio de 2026 crecieron de forma notable, con un incremento de más del **280%** en el total facturado en comparación con junio de 2025.
> - El volumen de facturas más que se duplicó, pasando de 25.803 a 59.842 transacciones.
> - El ticket promedio también subió cerca de un **64%**, lo que muestra un mayor valor por cada operación.
>
> ```savi-chart
> {
>   "type": "bar",
>   "title": "Comparativo Ventas: Junio 2025 vs Junio 2026",
>   "labels": ["Junio 2025", "Junio 2026"],
>   "series": [
>     { "name": "Total Facturado (Millones)", "data": [845.37, 3214.44] }
>   ]
> }
> ```

### ❌ Periodo sin datos (no inventar comparación)

**Pregunta:** ¿Cómo vamos en ventas de enero a marzo de 2026 comparado con el mismo periodo de 2025?

**Se espera:** Da el total de 2026 ($6.862 M), dice que no hay datos de 2025 en ese periodo y desde cuándo hay datos

**Respuesta de SAVI** (14.2 s, conversación `d318d009-3a5e-432e-8ec7-5661d090366d`):

> Para el periodo de **enero a marzo de 2026**, las ventas totales alcanzaron los **$6.862.574.932,80**, distribuidos en 133.007 facturas, con un ticket promedio de **$51.595,59**.
>
> Tené en cuenta que en el sistema **no tenemos registros de ventas previos a mayo de 2025** (el historial disponible arranca en mayo de 2025), por lo que no es posible hacer una comparación directa frente al primer trimestre de 2025. 
>
> Acá tenés el desglose mes a mes del primer trimestre de 2026:
>
> | Mes | Total facturado | Cantidad de facturas | Ticket promedio |
> |---|---|---|---|
> | Enero 2026 | $1.897.019.690,46 | 40.449 | $46.901,52 |
> | Febrero 2026 | $2.253.505.766,38 | 43.682 | $51.588,89 |
> | Marzo 2026 | $2.712.083.275,96 | 48.877 | $55.487,92 |
> | **Total / Promedio** | **$6.862.608.732,80** | **133.008** | **$51.595,74** |
>
> **Lectura:**
> - El trimestre muestra una **tendencia alcista sostenida**: marzo fue el mes con mayor facturación, representando el **39,5%** del total del trimestre, superando en un **20,3%** lo registrado en febrero.
> - El volumen de facturas y el ticket promedio también crecieron mes a mes, pasando de $46.901 en enero a $55.488 en marzo.
>
> ```savi-chart
> {
>   "type": "bar",
>   "title": "Ventas Enero - Marzo 2026",
>   "labels": ["Enero", "Febrero", "Marzo"],
>   "series": [
>     { "name": "Total Facturado ($)", "data": [1897019690.46, 2253505766.38, 2712083275.96] }
>   ]
> }
> ```
>
> ¿Te gustaría que comparemos este trimestre con otro periodo disponible, como mayo a julio de 2025?

### ✅ Imagen de trabajo (captura de error del ERP)

**Pregunta:** ¿Qué dice esta imagen?

**Se espera:** Lee la captura: error 4021, producto HE0151 sin saldo

**Respuesta de SAVI** (3.9 s, conversación `00c46ecb-9077-4349-a0ec-8b79bdbf9a6e`):

> La imagen muestra un mensaje de error del módulo de facturación del ERP:
>
> > **SEO ERP - Facturación**
> > **Error 4021:** producto HE0151 sin saldo en bodega
>
> Este error sale al intentar facturar un producto que en este momento no tiene existencias registradas en la bodega desde la que estás despachando. 
>
> ¿Querés que revisemos el inventario de ese producto para ver en qué bodega hay saldo o si necesitamos hacer un ingreso?

### ✅ Imagen ajena al trabajo (videojuego)

**Pregunta:** ¿Qué dice esta imagen?

**Se espera:** No la describe; dice que es un juego/escritorio no relacionado y pide una captura del ERP

**Respuesta de SAVI** (3.6 s, conversación `5d5a26ca-292a-45c3-bf40-46c9152320d0`):

> Esa imagen parece una captura de un videojuego. La verdad es que no está relacionada con el ERP ni con la empresa. 
>
> Si tenés alguna captura del sistema, un error, una factura o un documento de trabajo, mandamela y con gusto le damos una vuelta.

### ✅ Pregunta fuera de alcance

**Pregunta:** ¿Quién ganó el mundial de 2022?

**Se espera:** Rechazo estándar

**Respuesta de SAVI** (3.0 s, conversación `e9210c8e-dae6-4c2b-80b2-4ad3526e86ef`):

> Soy SAVI, el asistente del ERP de SEO Group. Solo puedo ayudarte con temas del producto y de tu empresa dentro del sistema. ¿En qué del ERP te puedo ayudar?

### ✅ Glosario

**Pregunta:** ¿Qué es la UVT?

**Se espera:** Definición del glosario

**Respuesta de SAVI** (3.3 s, conversación `f396accd-a740-4a27-aca4-7060c5805968`):

> La **UVT** (Unidad de Valor Tributario) es la unidad de medida que utiliza la DIAN para expresar los valores de las obligaciones fiscales, topes de ingresos, sanciones y bases de retención en la fuente. Su valor en pesos colombianos se actualiza cada año según la inflación.

