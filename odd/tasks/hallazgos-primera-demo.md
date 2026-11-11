# Hallazgos de la primera demo con cliente

**Locator:** `odd/tasks/hallazgos-primera-demo.md` · Engram `odd/hallazgos-primera-demo/tasks`.
**Rama de trabajo:** `staging`.
**Origen:** demo del 2026-11-11 con un cliente de llantas y repuestos (base `pg_Imporllantas`, respaldo local en `savi-datos`). Conversación exportada y tres capturas revisadas en la sesión.

## Objetivo

Que SAVI le facilite el trabajo al usuario sin dejar de ser seguro:

- entrega los datos que el usuario tiene derecho a ver;
- dice con claridad cuando un resultado está incompleto, y permite obtenerlo completo;
- genera documentos (Word, PDF, Excel) con la información pedida;
- no se queda sin responder.

## Cómo se trabaja

1. **Primero se analiza, después se implementa.** Cada punto tiene su documento de análisis con el problema, la evidencia, las opciones, la decisión y los criterios de aceptación. Se implementa recién cuando están los cuatro documentos.
2. Un punto a la vez, en el orden de abajo.
3. Commits y push a `staging` sin pedir OK en cada paso. Build, tags, servidor y `main` siguen pidiendo OK.
4. Trabajo inline, sin subagentes, por preferencia del usuario.
5. Textos visibles de usted (CLAUDE.md §14).
6. **Modo de pruebas:** TDD apagado (no hay configuración que lo active). Pruebas funcionales con `uv run pytest` y `pnpm vitest`; Ruff y Pyright strict en el backend.

## Puntos

### P1. Datos restringidos que el usuario sí debería poder ver

- **Problema:** el validador del SQL libre y el catálogo semántico bloquean siempre identificación, teléfono, celular, correo y dirección de los terceros (`free_query/application/sql_validator.py:92`, `data_query/infrastructure/catalog/terceros.py:3`). El cliente necesita listados de clientes y proveedores con sus datos de contacto.
- **Decisión del usuario (2026-11-11):** los ve quien tenga permiso en el módulo Terceros del ERP y los administradores de SAVI.
- **Alcance del análisis:** no solo terceros. Identificar los demás datos que hoy se bloquean o no se exponen y que el usuario probablemente quiera sacar, con el permiso del ERP que corresponde a cada uno.
- **Síntomas a corregir también:** el modelo insiste contra el bloqueo (7 consultas fallidas seguidas), explica el bloqueo de forma distinta cada vez y lee de una captura lo que la base no le deja devolver.
- **Documento:** `docs/plataforma/10-datos-por-permiso.md`.

### P2. Resultados recortados que parecen completos

- **Problema:** el detalle devuelve como máximo 30 filas (`data_query/domain/semantic_model.py:122`) y el SQL libre 50 (`free_query/domain/policy.py:16`). "Regáleme la base de clientes" devolvió 30; el análisis de baja rotación omitió referencias porque la consulta de inventario trajo una parte y el criterio fue malo. La descarga de la tabla exporta solo lo visible.
- **Documento:** `docs/plataforma/11-resultados-completos.md`.

### P3. Generación de documentos (Word, PDF, Excel)

- **Pedido del cliente:** que SAVI genere documentos con la información solicitada.
- **Hoy:** solo la descarga CSV/Excel de cada tabla del chat (`frontend/src/modules/chat/components/SaviTable.vue`).
- **Alcance del análisis:** cómo hacerlo correctamente, sin fallas de seguridad ni fuga de datos (permisos de P1, límites de P2, inyección en fórmulas de Excel, contenido que el modelo no debe poder colar, tamaño, dónde se guarda y quién lo descarga).
- **Documento:** `docs/plataforma/12-generacion-de-documentos.md`.

### P4. Turnos que terminan sin respuesta

- **Problema:** "No pude generar una respuesta para esa consulta" después de dos consultas exitosas al ERP, y dos turnos previos sin ninguna respuesta. Ese texto solo lo emiten los runners de OpenAI y Gemini (bloqueo de seguridad, error antes del primer token, o 429/5xx tras el reintento).
- **Falta:** el `savi.log` del equipo de la demo (el de este equipo termina el 2026-11-03), o reproducirlo con el respaldo de la base.
- **Documento:** `docs/plataforma/13-turnos-sin-respuesta.md`.

## Checklist

**Fase A. Análisis (un documento por punto)**

- [ ] A1. Documento de P1: inventario de datos restringidos, permisos del ERP y diseño.
- [ ] A2. Documento de P2: límites, honestidad sobre lo incompleto y obtención completa.
- [ ] A3. Documento de P3: diseño seguro de la generación de documentos.
- [ ] A4. Documento de P4: causa del fallo y cómo evitarlo.
- [ ] A5. Repaso conjunto y orden de implementación (P1 y P2 condicionan a P3).

**Fase B. Implementación:** se arma al cerrar la Fase A, con tareas por punto.

## Estado

| Etapa | Estado |
|---|---|
| Fase A | En curso: plan creado (2026-11-11). Sigue A1. |
| Fase B | Pendiente. |
