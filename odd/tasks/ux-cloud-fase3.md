# UX de Cloud: fase 3, detalles del cliente y de la instalación

## Objetivo

Que el detalle del cliente y el de la instalación se lean rápido y sirvan en una llamada de soporte. Hoy son páginas largas, con datos repetidos y seudónimos crudos.

## Por qué

Hallazgos de la revisión del 2026-11-18 (https://claude.ai/artifact/W37zhfJpXZ2JipayHNHsWA):

- **D1:** la Puesta en marcha ocupa media pantalla.
- **D2:** el Plan aparece dos veces.
- **D3:** Configuración son nueve tarjetas, con botones de texto en vez de interruptores.
- **D4:** Operación no muestra el uso por instalación.
- **N1:** las personas aparecen como seudónimos crudos.
- **N3:** la instalación no muestra su uso.
- **N4:** Revocar es un botón rojo principal.
- **A2:** cada regla de alerta ocupa una tarjeta grande.
- **M1:** en el celular, los filtros ocupan la primera pantalla.

D5 y N2 quedaron resueltos en la fase 1.

## Alcance

Rama `develop`. El usuario autorizó la fase 3 el 2026-11-18. Las instalaciones de los clientes no se tocan.

## Restricciones

- Los cambios al API son aditivos.
- "Persona N" es un número estable por cliente, según el orden en que cada persona apareció por primera vez. El seudónimo sigue disponible en un tooltip, para soporte.
- Revocar sigue enviando `REVOCAR`, que es el contrato del backend. La interfaz pide escribir el nombre de la instalación.
- Los textos visibles van de usted.

## Tareas

- [ ] **F3.1 Backend.**
  - Número de persona en `people` y `users`.
  - `GET /instances/{id}/metrics`.
  - `/instances` suma el costo y los errores de 30 días.
- [ ] **F3.2 Detalle de la instalación (N1, N3, N4).**
  - "Persona N" con tooltip y botón para copiar el seudónimo.
  - Uso propio: cifras y gráfico.
  - Revocar dentro de "Más acciones", confirmando con el nombre de la instalación.
- [ ] **F3.3 Operación del cliente (D4).** Turnos, costo y errores por instalación, y la versión marcada cuando está atrasada.
- [ ] **F3.4 Puesta en marcha (D1).** Barra compacta ("3 de 6") que se despliega al hacer clic y desaparece al completarse.
- [ ] **F3.5 Plan (D2).** Resumen con "Editar plan" en un diálogo, y los movimientos en una tabla.
- [ ] **F3.6 Configuración (D3).** Una sección a la vez, interruptores para los estados y campos cortos con prefijo US$.
- [ ] **F3.7 Reglas de alerta (A2).** Tabla compacta con regla, severidad, umbral e interruptor.
- [ ] **F3.8 Celular (M1).** Filtros plegables detrás de un botón "Filtros".

## Verificación

- Cloud backend: `pytest`, `ruff` y `pyright`. Revertir `app/shared/sync_v1.py` si `ruff format` lo toca.
- Cloud frontend: `vue-tsc`, `vitest` y Biome.
- Capturas en la Cloud local.

## Ruta y TDD

- **Ruta:** todo inline, por preferencia del usuario.
- **TDD:** no está configurado. Las pruebas van junto con cada cambio.

## Progreso

Sin empezar.
