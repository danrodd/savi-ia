# Cobertura del ERP: que SAVI sepa lo que sabe y lo que no

## Objetivo

Que SAVI responda bien sobre cualquier parte del ERP que el cliente use. Cuando no pueda consultarla, debe decirlo con honestidad, y nunca afirmar "no hay" sobre algo que no revisó.

## Problema

El 2026-11-24, soporte y un cliente reportaron dos conversaciones. Las copias están en `savi-datos/*.html`.

- **Anticipos de un tercero.** SAVI revisó cartera y facturas, concluyó que no había nada y pidió una captura. El anticipo existía: estaba en `Contabilidad.Anticipo`, que el catálogo no cubre. Lo encontró solo al final, con la consulta libre, después de varios fallos.
- **Informe de compras con IVA por tarifa.** Muchos turnos gastaron el tope de 12 consultas (en la pantalla aparece "×13") sin entregar nada. La consulta libre le muestra al modelo hasta 50 filas. Al agregar una columna, el informe perdía su estructura.

## Por qué pasa

Medido en la base de Imporllantas el 2026-11-24:

| Dato | Valor |
|---|---|
| Tablas del ERP / con datos en este cliente | 480 / 156, en 24 módulos |
| Tablas que usa el catálogo de SAVI | unas 15 (alrededor del 10 % de las que tienen datos) |
| Tablas con descripción en la base (`COMMENT`) | 25 |
| Funciones con reglas de negocio en la base | unas 190 |

Hay tres causas:

1. **El catálogo cubre solo** ventas, compras, cartera, inventario y terceros.
2. **El modelo no sabe dónde termina lo que conoce**, así que toma "no encontré en cartera" como "no existe".
3. **La consulta libre trabaja sin un mapa**: adivina tablas y columnas, falla y gasta el tope.

Además, la búsqueda de terceros compara contra un solo nombre (el comercial, la razón social o el primer nombre con el primer apellido), y muestra un nombre distinto del que aparece en los documentos del ERP.

## Alcance

- Los cambios que llegan a los clientes salen por `staging`, luego en una versión candidata y después por el actualizador.
- El usuario autorizó armar el plan el 2026-11-24. La implementación de cada fase espera su OK.

## Restricciones

- Siguen siendo como máximo 4 tools MCP. Lo nuevo entra como entidades del catálogo de `consultar_datos`.
- Los datos del ERP se leen solo en modo lectura y respetan los permisos de cada usuario.
- Los textos visibles van de usted.
- No se exponen al usuario el SQL ni los nombres internos de las tools.

## Plan

### Fase 1: honestidad sobre la cobertura (inmediata)

- [x] **C1.1 Mapa de cobertura en el prompt.**
  - Indicar qué entidades se pueden consultar y cuáles no.
  - Indicar qué significa "no encontré": en qué fuentes buscó.
- [x] **C1.2 Regla.**
  - No concluir que algo no existe cuando no está en el catálogo.
  - Avisar qué no se puede consultar.
  - No pedir capturas de lo que SAVI puede buscar.
- [x] **C1.3 Pruebas.** Preguntas fuera del catálogo, por ejemplo anticipos (hasta que existan), nómina o activos fijos. La respuesta debe nombrar lo revisado y lo que no.

### Fase 2: lo que los clientes ya están pidiendo

- [x] **C2.0 Devoluciones fuera de ventas y compras (hallazgo del 2026-11-25).**
  - El ERP guarda las devoluciones en la misma tabla que las facturas, con total positivo: tipo de documento 14 en venta y 13 en compra.
  - El catálogo solo excluía las anuladas, así que las sumaba como ventas o compras. En imporllantas eran 294 M de más en ventas y 116,6 M en compras; en frami, 1.297 M en ventas.
  - Ahora `ventas` y `compras` las excluyen, y tienen su propia entidad.
  - **Pendiente:** confirmar con el equipo del ERP qué cifra muestran sus informes de ventas (brutas o netas).

- [x] **C2.1 Anticipos** de clientes y de proveedores.
  - Valor, cruzado, saldo pendiente y si está anulado.
  - Filtros por tercero (cédula o nombre) y por fecha.
  - Tablas: `Contabilidad.Anticipo` y `Cartera.CruceAnticipoCliente` y `CruceAnticipoProveedor`. También `Contabilidad.DevolucionAnticipo`.
- [x] **C2.2 Notas de devolución** de venta y de compra, con la factura relacionada, el tercero y el desglose de IVA. Tablas: `CuentaCobrar.FacturaDevolucion` y `CuentaPagar.FacturaCompraDevolucion`, más sus variantes `Tercero*`.
- [x] **C2.3 IVA por tarifa en compras** (19 %, 5 %, excluido y exento), igual que en ventas.
- [x] **C2.4 Búsqueda de terceros.**
  - Por palabras, sin importar tildes ni el orden.
  - Que incluya segundos nombres y apellidos.
  - Mostrar el nombre completo como en el ERP.
- [x] **C2.5 "Todo sobre un tercero".** Cuando se pregunta por un tercero, SAVI revisa ventas, compras, cartera y anticipos, y dice qué revisó.

### Fase 3: informes completos

- [x] **C3.1 Exportes completos.** El Excel o CSV de una consulta libre trae todas las filas leídas, aunque el modelo vea solo 50. Antes, revisar `fetch_rows` y `max_rows`.
  - Hallazgo: la herramienta ya leía y guardaba hasta 10.000 filas (`fetch_rows = FULL_FETCH`). El corte venía del prompt, que tenía reglas de antes de la exportación:
    - "`LIMIT` obligatorio, máximo 50": el modelo escribía `LIMIT 50` y el Excel salía con 50 filas;
    - "Si pide todos los registros, NO lo hagas" y "no lo hagas ni con SQL libre": se negaba ("No puedo entregarle aquí el listado completo");
    - de paso, "sin `WITH`" y "≤ 1000 filas estimadas", que ya no aplican.
  - Cambios (route: inline, prompt + un parámetro de la herramienta):
    - el `LIMIT` lo decide la pregunta: un listado completo va sin `LIMIT`;
    - un listado completo se entrega: total, un top en el chat y la tabla completa para exportar;
    - columnas legibles: booleanos y códigos traducidos con `CASE`;
    - parámetro `exploracion` en `consultar_libre`: las consultas para ver valores no salen como tarjeta (`is_exploration`).
  - Pruebas: `test_system_prompt_coverage.py` y `test_schema_lookup_not_recorded.py`.
  - Comprobado en la app: "el plan de cuentas completo para Excel" da las 2.891 cuentas en una sola tarjeta, con la naturaleza como "Débito"/"Crédito" y el Excel de 72 KB. Antes: se negaba; después, tres tarjetas con `true`/`false`.
- [ ] **C3.2 Tope de consultas por turno.** Revisar las 12 consultas para informes largos, con medición: cuántos turnos llegan al tope y por qué.
  - Hecho en C3.3: las consultas de esquema (`information_schema`) tienen su propio cupo de 8 y no gastan las 12 de datos.
  - Pendiente: la medición con los datos de uso de Cloud. Hoy no hay acceso a ellos.
- [x] **C3.3 Informe que se amplía.** Al pedir otra columna, se conserva la estructura que ya tenía.
  - Reproducido el 2026-11-25: listado de compras de agosto de 2026, luego "agrégale la fecha de vencimiento" y luego "agrégale la retención en la fuente".
    - El vencimiento, que está en el catálogo, sale bien: mismas columnas, orden y 39 filas.
    - La retención, que no estaba en el catálogo, falla:
      - 13 consultas, 9 de ellas para buscar tablas; llega al tope;
      - solo actualiza 10 de 39 compras;
      - rehace el informe con SQL libre usando `valorGravadoIva` como base, y la base al 19 % del Excel sale igual al total, distinta a la del chat.
  - Cambios (route: inline; tres cambios acotados y ya entendidos):
    - retenciones en `compras` (`_retenciones.py`), por tipo: ReteFuente, ReteIVA, ReteICA y otras.
      - El tipo sale del código DIAN del indicador (`codigoImpuestoHKA` 06/05/07).
      - Sin código se mira la descripción, solo en esos casos: "RETEFUENTE … ZOMAC" de frami y "RETEICA CALI".
      - `retenciones` = `valorImpuestosRetencion`, que coincide con la suma de las líneas en las cuatro bases;
    - el prompt: "Ampliar un informe" repite la misma consulta con la columna nueva y, si rehace con SQL libre, compara las columnas que ya estaban. En SQL libre, la base es `subtotal` y no `valorGravadoIva`;
    - cupo aparte para las consultas de esquema (`TurnBudget(max_lookups=8)`).
  - Pruebas contra las cuatro bases:
    - las retenciones suman la cabecera;
    - una fila por factura;
    - el listado admite la columna;
    - la ReteFuente sin código se clasifica;
    - prompt y presupuesto.
  - Comprobado en la app: una sola consulta, las mismas columnas y las 39 compras, con la base correcta también en la tabla para exportar. Tras corregir la clasificación sin código, la 2781 tiene su ReteFuente de $161.020; lo cubre la prueba y no se repitió en la app.

### Fase 4: aprender de lo que preguntan

- [ ] **C4.1 Reporte de vacíos.** Juntar las preguntas que cayeron en consulta libre, las que fallaron y las que llegaron al tope. Las fuentes son la auditoría local de consultas y las métricas de Cloud (`free_query`, `finish_reason`).
- [ ] **C4.2 Rutina.** Cada mes, las más frecuentes pasan al catálogo (repetir la fase 2).

### Fase 5: diccionario del ERP

- [ ] **C5.1 Script** que recorre las bases de los clientes disponibles y arma un inventario por módulo y tabla:
  - columnas y relaciones;
  - cuántos clientes la usan y con cuántos registros;
  - qué funciones la tocan.
- [ ] **C5.2 Borrador de descripciones** generado desde los nombres, las relaciones, una muestra de datos y las funciones.
- [ ] **C5.3 Validación** con el equipo del ERP, módulo por módulo: corrigen el borrador, no escriben desde cero.
- [ ] **C5.4 Integración.** La consulta libre usa el diccionario en lugar de adivinar.

### Fase 6: reglas de negocio con el equipo del ERP

- [ ] **C6.1 Sesiones cortas por módulo** con quien lo conoce. Ejemplos de preguntas: cuándo un anticipo queda cruzado, qué estados anulan un documento, qué cuentas usa cada concepto.
- [ ] **C6.2 Código del ERP** solo para dudas puntuales que no resuelvan la base ni las sesiones.

## Orden y entregas

1. **Fases 1 y 2** en una sola versión. Resuelven los casos reportados y la respuesta falsa.
2. **Fase 3** en la siguiente versión.
3. **Fases 4 a 6** en paralelo y de forma continua. Dependen del equipo del ERP y de los datos de uso.

## Verificación

- Backend: `pytest`, Ruff y Pyright, y el test de registro de usted.
- Las pruebas del catálogo se corren contra las tres bases locales: imporllantas, frami y la de demo.
- Se repiten en local las preguntas de los casos reportados, con su evidencia.

## Ruta y TDD

- **Ruta:** inline, por preferencia del usuario.
- **TDD:** no está configurado. Las pruebas van junto con cada cambio.

## Progreso

- **2026-11-24:** se armó el plan.
- **2026-11-25:** el usuario autorizó las fases 1 y 2 y empezó la implementación en `staging`.
- **Decisiones de diseño:**
  - **De quién es cada anticipo** lo dice `General.Documento.tipo`, no el código del documento, porque los códigos cambian por cliente: 17 y 18 son anticipos de cliente y a proveedor; 46 y 47, sus devoluciones.
  - **IVA por tarifa en compras:**
    - la base es el `subtotal` de la línea, porque `valorGravadoIva` trae la base más el IVA;
    - exento y excluido se separan por `Inventario.IndicadorIva`;
    - se calcula con un `LATERAL` que da una fila por factura, para no inflar los totales.
  - **Nombre del tercero:**
    - la búsqueda usa el nombre comercial, `nombreCompleto` y cada parte del nombre;
    - se muestra `nombreCompleto`, que es el que figura en los documentos del ERP.

- **Commits:** `staging` f8c089f (catálogo) y a41f931 (prompt). Se integraron en `develop` con 8ee837f.
  - f8c089f también lleva cambios de formato de `ruff format` en tres archivos de `data_query`, sin cambio de comportamiento.
- **Pruebas:**
  - Backend completo: 1626 pasan y 14 se saltan.
  - `data_query`: 318 pruebas contra farmacias_similares, frami, sur_andina e imporllantas. Las nuevas cubren devoluciones, anticipos, IVA por tarifa y nombre completo.
  - Prueba de cobertura del prompt y registro de usted, en verde.
- **Prueba en vivo con frami** (SAVIQA@FRAMI, 2026-11-25):
  - **Anticipos por cédula (7692407):** una consulta; responde $510.000 pendientes en el ACC 1331 y no pide captura.
  - **"¿Qué tiene pendiente Wilson Ochoa Ríos?":** lo encuentra por el nombre completo. Revisa cartera, anticipos, ventas, compras y devoluciones, y dice qué revisó.
  - **Compras de octubre de 2025 con el IVA por tarifa:** una consulta, 47 compras con el desglose y el listado completo para descargar.
  - **Nómina (fuera del catálogo):** la explora con la consulta libre y responde "no puedo confirmar", no "no existe".
- **No se pudo reproducir el caso exacto del reporte:** la copia local de imporllantas no es la misma base del cliente que reportó (los AC 129 y 175 son de otros terceros).

- **Prueba en la app** (2026-11-25, preguntas distintas a las del script; cada cifra se revisó contra la base):
  - Ventas 2025: bruto $8.187.473.301,90, devoluciones $182.426.909,50, neto $8.005.046.392,40. Exacto.
  - "ayúdame a buscar anticipos de clientes de David Camilo Vásquez": lo encuentra aunque en el ERP sea "VASQUEZ MOLANO DAVID CAMILO". 2 anticipos, $10.405.900. Exacto.
  - "Todo lo pendiente con Sival Triplex": cuentas por pagar, 8 anticipos ($111.463.743), 725 compras y 20 devoluciones. Exacto.
  - Compras de julio a septiembre de 2026 con el IVA por tarifa: 85 de 85, con el listado completo para exportar.
- **Correcciones de esa prueba** (route: inline; cuatro cambios chicos y ya entendidos):
  - [x] El título de la tarjeta no muestra ids internos ni booleanos ("Tercero id 41, Pendiente True" pasa a "Pendiente"). Las entidades nuevas tienen título en español. Prueba: `test_result_titles.py`.
  - [x] El prompt pide copiar el nombre del ERP letra por letra. Antes escribió "VÁSQUEZ" con tilde y dijo que así figuraba.
  - [x] El prompt pide, cuando `consultar_libre` no devuelve nada, decir qué tabla revisó y si está vacía del todo. Antes, con la tabla de depreciación vacía entera, respondió solo "no encontré este mes".
  - [x] Las sugerencias de inicio son solo preguntas que el catálogo responde. Se quitaron nómina, contabilidad general, activos fijos y cartera financiera, que es otro módulo del ERP y no ve la entidad `cartera`. Prueba: `suggestions.spec.ts`.
  - Comprobado en la app: el nombre sale tal cual y la depreciación dice "Tampoco hay registros históricos en ese registro".
  - Pendiente: el manual de uso (`docs/manuales/01-manual-de-uso.html`) todavía trae como ejemplos el estado de resultados y el balance general.

## Próximo paso

- Publicar una versión candidata desde `staging` con estos cambios. Necesita OK.
- Confirmar con el equipo del ERP si sus informes de ventas muestran las cifras brutas o netas.
- Fase 3: informes completos.
