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

- [ ] **F2.1 Backend Resumen (R2, R3, R4).** `/overview` agrega:
  - `previous_usage`: el periodo anterior, de la misma duración;
  - `top_clients`: los 5 clientes con más turnos;
  - `trend_by_client`: los 3 principales y "Otros", por día.
- [ ] **F2.2 Backend Clientes (C1, C3).** `/clients` agrega:
  - el consumo de 30 días (turnos, personas activas y costo);
  - el resumen del plan;
  - las alertas abiertas por severidad;
  - las instalaciones que esperan la primera conexión;
  - un orden `attention`, que pasa a ser el predeterminado.
- [ ] **F2.3 Backend Instancias (I4).** `/instances` agrega los turnos de 30 días de cada instalación.
- [ ] **F2.4 Frontend Resumen (R1–R4).**
  - Franja "Requiere atención".
  - Cuatro cifras con su variación.
  - Barras apiladas por cliente.
  - "Clientes con más uso".
- [ ] **F2.5 Frontend Clientes (C1–C3).**
  - Plan, personas, turnos y costo.
  - Una etiqueta de instalaciones por caso.
  - Un punto de salud.
  - Orden por atención.
- [ ] **F2.6 Frontend Instancias (I4).** Icono de modo y turnos de 30 días.

## Verificación

- Cloud backend: `pytest`, `ruff` y `pyright`.
- Cloud frontend: `vue-tsc`, `vitest` y Biome.
- Capturas en la Cloud local.

## Ruta y TDD

- **Ruta:** todo inline, por preferencia del usuario (sin subagentes), aunque toca más de dos archivos.
- **TDD:** no está configurado. Las pruebas van junto con cada cambio.

## Progreso

Sin empezar.
