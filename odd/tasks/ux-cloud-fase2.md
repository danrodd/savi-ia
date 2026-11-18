# UX de Cloud: fase 2, Resumen y listas

## Objetivo

Que el staff abra la consola y sepa qué atender, y que la lista de clientes sirva para decidir a quién llamar.

## Por qué

La revisión del 2026-11-18 (https://claude.ai/artifact/W37zhfJpXZ2JipayHNHsWA) tiene estos hallazgos:

- **Resumen (R1–R4):**
  - cuenta las alertas sin decir cuáles son;
  - las cifras no tienen tendencia;
  - el gráfico es de una sola serie;
  - no hay ranking de clientes.
- **Clientes (C1–C3):**
  - no muestra el plan ni el consumo;
  - "0 / 0" y "nunca" mezclan casos distintos;
  - se ordena por código.
- **Instancias (I4):** no se ve el modo ni el uso.

## Alcance

Rama `develop`. El usuario autorizó la fase 2 el 2026-11-18. Las instalaciones de los clientes no se tocan.

## Restricciones

- No hay endpoints nuevos: se amplían `/overview`, `/clients` e `/instances`, y todos los campos nuevos son aditivos.
- "Requiere atención" usa las alertas abiertas que ya existen (`/alerts?status=open`), y solo se pide con el permiso `alerts.read`.
- El consumo es de los últimos 30 días, igual que el Resumen.
- Los textos visibles van de usted.

## Tareas

- [x] **F2.1 Backend Resumen (R2, R3, R4).** `/overview` agrega:
  - `previous_usage`: el periodo anterior, de la misma duración;
  - `top_clients`: los 5 clientes con más turnos;
  - `trend_by_client`: los 3 principales y "Otros", por día.
- [x] **F2.2 Backend Clientes (C1, C3).** `/clients` agrega:
  - el consumo de 30 días (turnos, personas activas y costo);
  - el resumen del plan;
  - las alertas abiertas por severidad;
  - las instalaciones que esperan la primera conexión;
  - un orden `attention`, que pasa a ser el predeterminado.
- [x] **F2.3 Backend Instancias (I4).** `/instances` agrega los turnos de 30 días de cada instalación.
- [x] **F2.4 Frontend Resumen (R1–R4).**
  - Franja "Requiere atención".
  - Cuatro cifras con su variación.
  - Barras apiladas por cliente.
  - "Clientes con más uso".
- [x] **F2.5 Frontend Clientes (C1–C3).**
  - Plan, personas, turnos y costo.
  - Una etiqueta de instalaciones por caso.
  - Un punto de salud.
  - Orden por atención.
- [x] **F2.6 Frontend Instancias (I4).** Icono de modo y turnos de 30 días.

## Verificación

- Cloud backend: `pytest`, `ruff` y `pyright`.
- Cloud frontend: `vue-tsc`, `vitest` y Biome.
- Capturas en la Cloud local.

## Ruta y TDD

- **Ruta:** todo inline, por preferencia del usuario (sin subagentes), aunque toca más de dos archivos.
- **TDD:** no está configurado. Las pruebas van junto con cada cambio.

## Progreso

Hecho el 2026-11-18.

- **Backend, f66d1ee (F2.1–F2.3).**
  - Pruebas: 374 existentes y 6 nuevas, junto con `ruff` y `pyright`. Las nuevas cubren el periodo anterior, el ranking, "Otros", el consumo por cliente, el orden por atención, el plan según el permiso y los turnos por instalación.
  - `test_client_lifecycle_and_listing` pasó a pedir `sort=code` de forma explícita, porque el orden predeterminado ahora es por atención.
  - `bogota_today` se movió a `metrics.queries` para evitar un import circular con alertas.
- **Frontend, d71ae5b (F2.4–F2.6).**
  - 228 pruebas pasan (antes 217), con `vue-tsc` y Biome sin errores.
  - La paleta de las series se validó con el script de dataviz. En modo claro tiene un aviso de contraste, que se compensa con la leyenda y con la tabla de clientes, que funciona como vista en tabla.
- **Capturas en la Cloud local:** Resumen, Clientes e Instancias.

## Decisiones

- **El plan en la lista exige `clients.billing`,** igual que la ficha del plan. Sin ese permiso, la columna no se muestra y el vencimiento no afecta la salud del cliente.
- **La variación va en tono neutro.** Que suban los turnos o el costo no es bueno ni malo por sí mismo, y el rojo queda reservado para lo crítico.
- **"Requiere atención" muestra solo las alertas abiertas,** no las reconocidas, porque esas ya tienen a alguien encargado.

## Próximo paso

Fase 3: los detalles del cliente y de la instalación (D1–D5, N1–N4, A2 y M1).
