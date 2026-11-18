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

- [x] A1. Documento de P1: `docs/plataforma/10-datos-por-permiso.md`. Hallazgos extra: módulos del ERP que SAVI no reconoce (`NOMINA`, `HERRAMIENTAS`, `CuentaPagar`), biometría y datos sensibles sin bloqueo en el SQL libre, `TerceroVip` por confirmar. Quedan 5 decisiones abiertas (§8).
- [x] A2. Documento de P2: `docs/plataforma/11-resultados-completos.md`. Propuesta central: conjuntos de resultados guardados en el servidor (el usuario recibe todo, el modelo una muestra y el total) y entidades de análisis para que los cruces los haga la base. 3 decisiones abiertas (§6).
- [x] A3. Documento de P3: `docs/plataforma/12-generacion-de-documentos.md`. El modelo entrega una especificación validada; las tablas referencian conjuntos (P2); generadores en Python puro (openpyxl, python-docx, reportlab); `info_empresa` pasa a `consultar_conocimiento` para que `entregar_archivo` entre en el límite de 4 herramientas. Exportación por botón y por el chat (decisión del usuario). 3 decisiones abiertas (§8).
- [x] A4. Documento de P4: `docs/plataforma/13-turnos-sin-respuesta.md`. Hallazgos: un turno con error sin texto no se guarda (`chat_turn.py:653`) y el mismo mensaje cubre 7 causas; en OpenAI, `response.failed` no se reintenta. La demo corrió con **OpenAI** (confirmado); no hay log, así que la causa se confirma reproduciendo el caso.
- [x] A5. Repaso conjunto y orden de implementación (abajo).

**Orden de la Fase B y por qué:**

1. **P4 primero:** es lo más chico y lo que más se nota. Un cliente que ve "No pude generar una respuesta" o preguntas sin respuesta pierde la confianza enseguida. No depende de nada.
2. **P1 después:** destraba lo que el cliente pidió (los teléfonos), corrige los módulos perdidos y deja listo el permiso por campo que usan P2 y P3.
3. **P2:** los conjuntos de resultados son la base de la exportación y de los documentos.
4. **P3 al final:** F1, la exportación por el chat, y F2, los documentos.

**Entrega:** commits por tarea a `staging`, como hasta ahora. Build, tags, `main` y servidor, con OK.

**Fase B. Implementación**

*P4. Turnos sin respuesta*

- [x] B1. Guardar el turno que falla sin texto (`finish_reason = error`, categoría, proveedor, modelo, consultas hechas). Mostrarlo al recargar con Regenerar, y omitirlo del contexto del turno siguiente.
- [x] B2. OpenAI: reintentar `response.failed` y `error` pasajeros y respetar `retry-after`. Reintentar solo la llamada al modelo si ya hubo consultas al ERP. Separar `_SECURITY_MESSAGE` de las fallas genéricas.
- [x] B3. Categorías de error con texto de usted y código de soporte (backend, frontend y manual de uso). Aplica a OpenAI, Gemini y Claude.
- [x] B4. Presupuesto de contexto: tope de consultas por turno (12) y recorte del historial antes del límite.
- [x] B5. Reproducir el caso de la demo con el respaldo de Imporllantas y OpenAI. Prueba de regresión.
- [x] B6. Vista de turnos fallidos en Administración.

*P1. Datos por permiso*

- [x] B7. Módulos del ERP sin tildes ni mayúsculas (`NOMINA`, `HERRAMIENTAS`, `CuentaPagar`) y log de los desconocidos.
- [x] B8. Permiso por campo en el catálogo (`required_modules` en `FieldDef`) y campos personales, comerciales y bancarios de terceros. Campos del tercero desde ventas, compras y cartera. Regla conservadora de `TerceroVip`.
- [x] B9. SQL libre: quitar el bloqueo de contacto para el administrador y armar la lista de prohibidos por tabla y columna.
- [x] B10. `PermissionDeniedError` con texto fijo, corte por turno y regla en el prompt.
- [x] B11. Auditoría de consultas con datos personales.

*P2. Resultados completos*

- [x] B12. Conjuntos de resultados guardados (dueño, vencimiento) y total exacto (`limit + 1` y `COUNT`).
- [x] B13. Vista previa en el chat desde los datos ("mostrando 30 de N") y botón Exportar (Excel, PDF y CSV generados en el servidor). Quitar `xlsx` del frontend.
- [x] B14. Entidad `inventario_rotacion` y campos de última compra o venta del tercero.
- [x] B15. SQL libre del administrador: `WITH` no recursivo y filtro previo por costo.

*P3. Documentos*

- [x] B16. `info_empresa` pasa a ser un tipo de `consultar_conocimiento`, medido con los 3 proveedores.
- [x] B17. `entregar_archivo`, tipo `exportar` (por el chat), con adjunto descargable en la respuesta.
- [x] B18. `entregar_archivo`, tipo `documento`: especificación validada, Word y PDF.
- [x] B19. Plantillas con la presentación de la empresa: nombre y logo tomados de `Empresa.Empresa` del ERP (validados y recomprimidos con Pillow), colores de SAVI. No hace falta cargar el logo en SAVI.

## Estado

| Etapa | Estado |
|---|---|
| Fase A | **Completa** (2026-11-11). Quedan decisiones menores abiertas en cada documento, ninguna frena el inicio. |
| Fase B | **Completa (2026-11-12).** B16–B19: `37692aa`, `2776576`, `f84d3a8`, `e956568`, `a22b0d5`. Prueba en la app real con OpenAI y la copia de Imporllantas (administrador, usuario con Terceros y usuario sin Terceros), con capturas en el informe. Arreglos que salieron de esa prueba: columnas por etiqueta, tablas pequeñas fuera del chat, títulos legibles, búsqueda de producto por código y frase fija de permiso en la descripción. Antes: B1–B3 en `c798dcf` (tests: `test_failed_turn.py`, `test_openai_integration.py`, `failedTurn.spec.ts`); B4 con `test_turn_budget.py`. B5: con OpenAI real y la copia local de Imporllantas, la pregunta que fallaba en la demo responde (557 productos), aunque con 8 consultas rechazadas antes (lo ataca B14/B15); con un OpenAI falso que responde 503, el log muestra 3 reintentos, el turno queda guardado con su código y se ve al recargar. B6: `/admin/failed-turns` y vista Turnos fallidos (`test_failed_turns.py`, `FailedTurnsView.spec.ts`). Pendiente menor: el turno fallido no guarda proveedor y modelo (solo llegan con `done`). B7 en `b4dac0a`. B8–B11: permiso por campo (`_tercero_fields.py`), SQL libre con lista de prohibidos, rechazo fijo con corte a los 2 rechazos y auditoría `savi.audit` (`test_field_permissions.py`, `test_sql_validator.py`, `test_turn_budget.py`). Desvío de la spec en `TerceroVip`: hoy vacía el dato para todo no administrador si el tercero está en la tabla (no distingue a los usuarios listados, porque el catálogo no recibe el usuario); la tabla está vacía en los tres clientes. B12–B15: módulo `documents` (conjuntos de resultados de hasta 10.000 filas, dueño y vencimiento a 90 días, exportación Excel/PDF/CSV/Word en el servidor con fórmulas neutralizadas), evento `data_tables` y tarjeta de datos en el chat, `xlsx` fuera del frontend, entidad `inventario_rotacion` (con la copia de Imporllantas: 124 productos con más de un año sin venta, la MICHELIN FORCE LTX con 509 días), SQL libre con `WITH` no recursivo y filtro por costo. Desvío: si hay más de 10.000 filas se informa "más de 10.000" en lugar de contar con `COUNT`. Ruta: inline (preferencia del usuario, sin subagentes). |
| Cierre | **Completo (2026-11-12).** Los tres desvíos quedaron resueltos: proveedor y modelo en el turno fallido (`05db5bd`), total exacto con `COUNT(*)` (`86db462`) y `TerceroVip` según el usuario que pregunta (`8e92a50`). Además: gráficos de barras en PDF y Word (`073148b`), migraciones con la base indicada (`a0711ae`) y las consultas a `information_schema` ya no aparecen como tablas en el chat (`1f88fd7`, salió de la prueba en la app). Backend: 1.494 en verde + 5 nuevas; frontend: 354. Informe con capturas: https://claude.ai/artifact/2uruCZvZJKzHjvKkTB3DEX. |
