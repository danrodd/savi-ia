# Vacíos del catálogo (fase 4 de cobertura del ERP)

## Objetivo

Saber qué preguntas el catálogo de datos no cubre, para sumarlas cada mes (fase 4 de `odd/tasks/cobertura-erp.md`: C4.1 reporte y C4.2 rutina).

## Problema

- Cuando el catálogo no alcanza, SAVI cae en la consulta libre, falla o gasta el tope de consultas.
- Hoy nadie ve esos casos juntos.
- El texto de las preguntas no sale de la instalación del cliente, por privacidad: a Cloud solo llega el resultado de cada consulta libre (`free_query_source.py`).

## Decisión del usuario (2026-11-25)

**Local + tablas a Cloud:**
- una página en Administración de cada instalación, que agrupa los vacíos y se exporta;
- a Cloud solo los nombres de las tablas del ERP que tocó cada consulta libre, sin preguntas ni valores, para ver entre todos los clientes qué conviene sumar.

## Alcance

**Vacíos que se cuentan:**
- **Consulta libre:** la pregunta se resolvió con SQL libre. Sin contar las de esquema ni las exploratorias.
- **Consulta fallida:** consulta libre rechazada o con error.
- **Tope de consultas:** el turno gastó el cupo y la siguiente consulta se rechazó.

**No incluye:** los turnos sin respuesta. Ya los muestra Administración → Turnos fallidos, y el reporte enlaza a esa página.

**Ramas:**
- la parte local (V1–V3) va en `staging` y se integra en `develop`;
- la de Cloud (V4–V5) va solo en `develop`, porque `cloud_link`, `contracts/` y `cloud/` no existen en `staging`.

## Restricciones

- **Privacidad:** a Cloud nunca viajan preguntas, SQL ni valores (RNF-04).
  - `tables` es un campo nuevo en `data` de `free_query/1`, así que es un cambio de contrato con revisión de privacidad (`contracts/sync/v1/README.md`).
  - Solo nombres `Esquema.Tabla` con un patrón estricto y un máximo de entradas.
- **Orden de despliegue:** Cloud se despliega antes que las instalaciones. Un Cloud viejo rechaza (`extra="forbid"`) el evento que traiga `tables`.
- **Permisos:** la página es solo para el administrador de la empresa y se acota a su base, como Turnos fallidos y Piloto.
- Cada texto visible va de usted.

## Tareas

- [x] **V1 Tablas de una consulta.** `referenced_tables(sql)` con sqlglot, que excluye los CTE e `information_schema`. Pruebas.
  - `app/modules/free_query/application/referenced_tables.py`: solo identificadores `[A-Za-z0-9_]`, máximo 20. Pruebas en `test_referenced_tables.py` (5): la consulta del 2026-11-25, el esquema, que no se filtren valores, SQL ilegible y el tope. Route: inline.
- [x] **V2 Reporte local (backend).**
  - Módulo `catalog_gaps`: caso de uso y lector SQLAlchemy sobre `audit_query` y `messages`.
  - Rutas `GET /admin/catalog-gaps` y `GET /admin/catalog-gaps/export.csv`.
  - Agrupa por pregunta: tipo de vacío, veces, última vez y tablas.
  - Hecho (route: inline):
    - el módulo `app/modules/catalog_gaps` en domain, application e infrastructure, más el router en `main.py` y `admin/catalog-gaps` en `_API_PREFIXES`;
    - la pregunta es el mensaje del usuario de ese turno, no la `pregunta_usuario` del modelo;
    - las consultas de esquema no cuentan;
    - "veces" = conversaciones distintas;
    - el tope se detecta cuando el turno pasa el cupo con todas las consultas al ERP y la última se rechazó. Así vale para la regla vieja, en la que las de esquema gastaban el mismo cupo.
  - Pruebas: `tests/unit/modules/catalog_gaps/test_catalog_gaps.py` (7), sobre SQLite:
    - agrupa por la pregunta del usuario;
    - consulta fallida y tope;
    - otra base y conversación borrada;
    - detección del tope;
    - normalización de la pregunta;
    - CSV contra la inyección de fórmulas;
    - periodo.
  - Probado con la base local del agente, el 2026-11-25 en frami: 7 turnos de consulta libre y 1 que llegó al tope.
    - Plan de cuentas: 3 veces, `Contabilidad.PlanContable`.
    - Depreciación: 2 veces, `ActivoFijo.DepreciacionRegActivo`.
    - Retención: consulta libre y tope.
    - Nómina: `Nomina.LiquidacionNomina`.
- [x] **V3 Página "Vacíos del catálogo" (frontend).**
  - Ruta `admin/vacios-catalogo` y enlace en el menú.
  - Periodo, resumen por tipo, tabla, exportar CSV y enlace a Turnos fallidos.
  - Hecho (route: inline):
    - `CatalogGapsView.vue`, `catalogGapsService.ts`, la ruta `admin/vacios-catalogo` y el enlace "Vacíos del catálogo" en el menú;
    - la página tiene totales por tipo, tablas más consultadas, la tabla por pregunta, periodo, CSV y enlace a Turnos fallidos.
  - Pruebas: `CatalogGapsView.spec.ts` (2). La suite del frontend da 359 de 359; `vue-tsc` y Biome, limpios.
- [x] **V4 Contrato y envío a Cloud.**
  - `tables` opcional en `free_query/1`: JSON Schema, fixtures, modelos de los dos lados y prueba de privacidad.
  - La instalación lo manda.
  - Cloud lo guarda (migración).
  - Hecho (route: inline):
    - **Contrato:** `tables` opcional en `free_query/1`. Patrón `Esquema.Tabla`, máximo 20 y sin repetir. Fixture válido actualizado y fixture inválido `table_with_values`. Aprobado en las listas blancas de privacidad de los dos lados y documentado en `contracts/sync/v1/README.md`, con el orden de despliegue: Cloud primero.
    - **Instalación:** `FreeQuerySource` lee `sql` solo para `referenced_tables` y manda los nombres.
    - **Cloud:** guarda `ev_free_queries.tables` (migración `0011`).
  - Pruebas:
    - instalación, `cloud_link`: 267, incluida una que comprueba que el evento lleva las tablas y nada de la consulta;
    - Cloud: contrato, privacidad e ingesta, dentro de la suite completa de 384.
- [x] **V5 Vista en Cloud.** Ranking de tablas consultadas por SQL libre entre todos los clientes, por periodo.
  - Hecho (route: inline):
    - `MetricsQueries.free_query_tables` cuenta consultas y clientes distintos por tabla, ordenados primero por clientes;
    - la ruta `GET /console/api/catalog-gaps` usa el permiso `overview.read`;
    - el Resumen de la consola tiene la tarjeta "Lo que le falta al catálogo", con el top 10.
  - Pruebas:
    - Cloud backend: el ranking entre dos clientes y que ignore los eventos sin `tables`. Suite de 384, más la nueva.
    - Consola: `overview-lists.spec.ts`. Suite de 239; `vue-tsc` y Biome, limpios.
- [x] **V6 Rutina mensual (C4.2).** Guía de soporte: exportar, revisar el ranking y llevar las más frecuentes al catálogo (repetir la fase 2).
  - Hecho: `docs/plataforma/14-vacios-del-catalogo.md`, con las señales, dónde mirar (Cloud y cada cliente), seis pasos y qué no hacer.

## Criterios de aceptación

- La página muestra los tres tipos de vacío del periodo, agrupados por pregunta, con las tablas que se tocaron. El CSV trae lo mismo.
- Un usuario que no es administrador no la ve, y la página no mezcla bases.
- El evento `free_query/1` con `tables` pasa el contrato y la prueba de privacidad, y uno con SQL sigue rechazándose.
- Cloud muestra las tablas más consultadas entre clientes sin ninguna pregunta.

## Checks

- Backend: `uv run pytest`, Ruff y Pyright strict en lo cambiado.
- Frontend: `npx vitest run`, `vue-tsc` y Biome.
- Cloud: sus pruebas de backend y de consola.
- Prueba en la app con la base local.

## Modo de trabajo

- TDD no configurado: checks funcionales por tarea.
- Inline, sin subagentes, por preferencia del usuario.
- Commits directos por tarea, como el resto del trabajo: `staging` o `develop` según la rama de cada tarea.
- Estimado: unas 1.500 líneas en total, a partes iguales entre backend local, frontend y Cloud.

## Progreso

- 2026-11-25: V1–V6 hechos.
  - `staging`: eef701b, a6ee9d5, el commit de V3 y c1a236f.
  - `develop`: la integración e969d85; 1ded270, el import de `@savi/ui`; 436e3c0 (V4); 4e4afa9 (V5); y V6.
  - Pendiente: que Cloud se despliegue antes que las instalaciones con `tables` (necesita OK), y hacer la primera rutina mensual cuando haya datos reales de clientes.

- 2026-11-25: plan creado tras la exploración. Datos disponibles:
  - `audit_query` (pregunta, SQL, resultado);
  - `messages.tool_invocations`, con `status` por herramienta: el turno que llega al tope termina en `error`.
