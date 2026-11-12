# 13 — Turnos que terminan sin respuesta

**Estado:** análisis (Fase A del plan `odd/tasks/hallazgos-primera-demo.md`). La causa exacta de la demo **está pendiente** de confirmar con el log del equipo donde se hizo (§6).
**Origen:** demo con cliente del 2026-11-11.

## 1. Lo que se vio

Al final de la conversación, tres mensajes seguidos del usuario:

1. "amplía el rango de búsqueda a llantas que no se han vendido hace más de 2 años": **sin respuesta**;
2. "¿Por qué?": **sin respuesta**;
3. "Busca los productos que no se han movido desde hace más de un año y que presenten existencias en el inventario" (editado): "Consultó el ERP ×2", y luego **"No pude generar una respuesta para esa consulta."**

En la exportación de la conversación, los dos primeros quedaron sin ninguna respuesta del asistente.

## 2. Hallazgo 1: un turno que falla no deja rastro

`chat/application/use_cases/chat_turn.py:653` guarda el mensaje del asistente **solo si tiene texto** (`accumulator.has_content()`). Si el turno termina en error antes del primer texto, pasa esto:

- **no se guarda nada:** ni el error, ni las consultas al ERP que sí se hicieron, ni el proveedor, ni el modelo;
- **al recargar,** la pregunta del usuario aparece sin respuesta. Es lo que muestran los dos primeros mensajes: casi seguro, fallaron igual que el tercero, y su error solo se vio mientras la pantalla estaba abierta;
- **el turno siguiente** le manda al modelo dos preguntas seguidas del usuario sin respuesta en el medio, lo que confunde ("¿Por qué?" de qué);
- **soporte no tiene qué mirar** en la base de datos. Solo queda lo que haya en el `savi.log` del equipo.

## 3. Hallazgo 2: el mismo mensaje tapa causas muy distintas

"No pude generar una respuesta para esa consulta." **solo lo emiten los runners de OpenAI y Gemini.** El de Claude no lo tiene, así que la demo corrió con uno de esos dos. Se emite en todos estos casos:

| Runner | Causa | Reintenta | Dónde |
|---|---|---|---|
| OpenAI | El stream trae `response.failed` o `error` (error del servidor, límite de uso dentro del stream) | **No.** Va directo al mensaje, aunque sea un error pasajero. | `openai/runner.py:246-264` |
| OpenAI | El modelo se negó (`refusal`) | No | `openai/runner.py:329` |
| OpenAI | Excepción pasajera (429, 5xx) después de los reintentos y de los modelos de respaldo | Sí, con espera creciente | `openai/runner.py:287-315` |
| OpenAI | Cualquier otra excepción antes del primer texto | No | `openai/runner.py:316-326` |
| Gemini | Bloqueo de seguridad (`SAFETY`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`) | No | `gemini/runner.py:299` |
| Gemini | 429 o 503 después de los reintentos y de los modelos de respaldo | Sí | `gemini/runner.py:247-282` |
| Gemini | Cualquier otra excepción antes del primer texto | No (salvo el caso del razonamiento) | `gemini/runner.py:287-296` |

Además, en OpenAI la constante se llama `_SECURITY_MESSAGE` y se usa también para fallas que no tienen nada que ver con seguridad. El manual de uso le dice al usuario "reformúlela sin datos personales" (`docs/manuales/01-manual-de-uso.html:460`), lo que en este caso lo manda a buscar el problema donde no está.

## 4. Causas probables en la demo

Sin el log no se puede afirmar. Por la forma de la conversación, en orden de probabilidad:

1. **Límite de tokens por minuto del proveedor (429).** La conversación era larga y los turnos anteriores hicieron 10, 12 y 14 consultas al ERP, cada una con tablas. Todo eso vuelve a viajar como historial, y los turnos que fallaron llegaron justo después de los más pesados. En OpenAI, si el límite llega como evento del stream y no como excepción, no se reintenta (hallazgo 2, primera fila).
2. **Error pasajero del servidor del proveedor** durante el stream, sin reintento por la misma razón.
3. **Bloqueo o negativa del proveedor:** menos probable, porque las preguntas eran de inventario y no tenían nada sensible.

## 5. Diseño propuesto

### 5.1 Ningún turno se pierde

- El mensaje del asistente se guarda **siempre**, también cuando termina en error y sin texto. Lleva `finish_reason = error`, la categoría del error, el proveedor, el modelo y las consultas que alcanzó a hacer.
- En el historial se ve como "No se pudo completar esta respuesta", con **Regenerar**.
- Al armar el contexto del turno siguiente, los turnos fallidos se omiten o se marcan, para que el modelo no reciba preguntas sin respuesta.

### 5.2 Reintentar todo lo pasajero

- En OpenAI, `response.failed` y `error` se clasifican igual que las excepciones: 429 y 5xx se reintentan con espera y se pasa al modelo de respaldo.
- Si el proveedor indica cuánto esperar (`retry-after`), se respeta, dentro de un tope.
- Si el error ocurre **después de consultas al ERP ya hechas**, se reintenta solo la llamada al modelo, con los resultados ya obtenidos, sin repetir las consultas.

### 5.3 Contexto acotado

Es lo que más previene el 429 por tokens.

- Lo que vuelve al modelo de cada consulta es una muestra y el total (P2), no la tabla entera.
- El historial que se reenvía tiene un presupuesto de tokens: los turnos viejos se resumen o se recortan antes de llegar al límite, en lugar de fallar.
- Un turno tiene un máximo de consultas al ERP. El corte por consulta repetida o rechazada (P1, §6.4) evita bucles como las 14 consultas de un turno.

### 5.4 Mensajes que dicen qué pasó

Una categoría por causa, con un texto de usted que diga qué hacer:

| Categoría | Texto propuesto |
|---|---|
| Proveedor saturado o con límite (429, 5xx) | "El servicio de inteligencia artificial está saturado en este momento. Espere un minuto y toque Regenerar." |
| Bloqueo o negativa del proveedor | "El proveedor de inteligencia artificial no quiso responder esta consulta. Reformúlela con otras palabras." |
| Sin créditos o clave inválida | Los que ya existen, para el administrador. |
| Falla interna | "No pude completar la respuesta por un problema interno. Toque Regenerar; si se repite, avise a soporte con el código <código>." |

- El **código de soporte** es un identificador corto del turno que también queda en el log y en el mensaje guardado. Así soporte encuentra la causa sin pedir el equipo.
- El manual de uso se actualiza con estas categorías.

### 5.5 Diagnóstico sin depender del equipo

- Los turnos fallidos quedan en la base (5.1), con categoría, proveedor, modelo, código HTTP, iteración y cantidad de consultas.
- Una vista en **Administración** lista los últimos turnos fallidos, igual que ya se ven las actualizaciones. El administrador del cliente puede mandarnos esa información sin buscar archivos.

### 5.6 Reproducir el caso de la demo

- Se restaura el respaldo de la base del cliente (`savi-datos`) en el Postgres local.
- Se repite la conversación con el mismo proveedor y el mismo modelo, hasta reproducir el error con el log a la vista.
- El caso queda como prueba de regresión (por lo menos la clasificación de errores con respuestas simuladas del proveedor).

## 6. Evidencia que hace falta

1. El **`savi.log`** del equipo de la demo, en `%LOCALAPPDATA%\SAVI\savi.log`. Las líneas `openai_*` o `gemini_*` del 2026-11-11 entre las 16:30 y las 17:00 dicen la causa exacta.
2. **El proveedor y el modelo** activos en esa instalación (se ven en Administración → Proveedores).
3. Si no hay log, la reproducción de §5.6.

## 7. Criterios de aceptación

1. Un turno que falla antes del primer texto queda guardado, se ve al recargar con su mensaje y **Regenerar**, y no confunde al turno siguiente.
2. Un `response.failed` pasajero de OpenAI se reintenta (test con respuestas simuladas).
3. Un error después de dos consultas al ERP reintenta solo la llamada al modelo, sin repetir las consultas (test).
4. Cada categoría muestra su texto. Ninguna falla genérica le dice al usuario "sin datos personales".
5. El código de soporte del mensaje aparece en el log y en la vista de Administración.
6. Una conversación tan larga como la de la demo no se corta por exceso de contexto: el historial se recorta antes.
7. El caso de la demo, reproducido, termina con respuesta.

## 8. Decisiones abiertas

1. **Cuántas consultas al ERP admite un turno.** Propuesta: 12. Al llegar al tope, el modelo responde con lo que tiene y dice qué faltó.
2. **Presupuesto del historial.** Propuesta: medir con las tres familias de modelos y fijarlo por proveedor en la configuración.
