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
- [ ] **V2 Reporte local (backend).**
  - Módulo `catalog_gaps`: caso de uso y lector SQLAlchemy sobre `audit_query` y `messages`.
  - Rutas `GET /admin/catalog-gaps` y `GET /admin/catalog-gaps/export.csv`.
  - Agrupa por pregunta: tipo de vacío, veces, última vez y tablas.
- [ ] **V3 Página "Vacíos del catálogo" (frontend).**
  - Ruta `admin/vacios-catalogo` y enlace en el menú.
  - Periodo, resumen por tipo, tabla, exportar CSV y enlace a Turnos fallidos.
- [ ] **V4 Contrato y envío a Cloud.**
  - `tables` opcional en `free_query/1`: JSON Schema, fixtures, modelos de los dos lados y prueba de privacidad.
  - La instalación lo manda.
  - Cloud lo guarda (migración).
- [ ] **V5 Vista en Cloud.** Ranking de tablas consultadas por SQL libre entre todos los clientes, por periodo.
- [ ] **V6 Rutina mensual (C4.2).** Guía de soporte: exportar, revisar el ranking y llevar las más frecuentes al catálogo (repetir la fase 2).

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

- 2026-11-25: plan creado tras la exploración. Datos disponibles:
  - `audit_query` (pregunta, SQL, resultado);
  - `messages.tool_invocations`, con `status` por herramienta: el turno que llega al tope termina en `error`.
