# DB_ACCESS_DESIGN — Cómo SAVI accede a la base de datos del ERP

> Documento de decisión arquitectónica (ADR). Explica **cómo** el agente
> SAVI consulta los datos del cliente, **por qué** se eligió este enfoque
> y **qué alternativas** se descartaron. Acompaña a [`DB_MAP.md`](DB_MAP.md)
> (el mapa de la BD) y a [`FRONTEND_CHAT_SPEC.md`](FRONTEND_CHAT_SPEC.md).

Estado: **propuesto** (pendiente de implementación). Última revisión: 2026-05.

---

## 1. El requerimiento

El cliente quiere que SAVI **responda preguntas sobre sus datos**: la
factura de un cliente, las ventas del mes, el stock de un producto, la
cartera vencida, etc. Dos usos previstos:

1. **Consulta de datos** (este documento): el usuario pregunta en lenguaje
   natural y SAVI consulta la BD y presenta la respuesta interpretada.
2. **Soporte** (futuro): primer filtro de soporte técnico del ERP. No se
   aborda aquí.

### La tensión central

- El cliente pide **libertad**: que SAVI pueda responder casi cualquier
  pregunta sobre la data, no un menú rígido.
- Pero hay un riesgo de seguridad **no negociable**: el usuario **no debe
  poder extraer datos crudos en bloque** ("dame 100 registros de ventas",
  "exporta todos los clientes"). Eso es exfiltración de datos y un vector
  de ataque para romper el agente.

Este diseño resuelve esa tensión sin caer en SQL libre.

---

## 2. Alternativas evaluadas

Se investigó el estado del arte (2025) y se auditó un proyecto de
referencia que intentó resolver lo mismo. Cinco enfoques, de menos a más
seguro:

| # | Enfoque | Seguridad | Flexibilidad | Veredicto |
|---|---------|-----------|--------------|-----------|
| A | **Text-to-SQL crudo** — el LLM ve el schema y genera SQL libre que se ejecuta | Muy baja | Máxima | ❌ Descartado |
| B | **Text-to-SQL + validador AST + row cap** (el enfoque del proyecto de referencia) | Baja-media | Alta | ❌ Descartado |
| C | **Text-to-SQL sobre VIEWS pre-aprobadas + GRANTs de BD** | Media-alta | Alta | ⚠️ Fallback |
| D | **Semantic Layer** (métricas/dimensiones en DSL determinístico, compilador a SQL) | Alta | Media-alta | ✅ Núcleo elegido |
| E | **Tools curadas / parameterized queries** (una tool por pregunta, SQL hardcoded) | Muy alta | Baja | ✅ Complemento |

### Por qué se descartó A (SQL libre crudo)

OWASP ranqueó **prompt injection como la vulnerabilidad #1 en LLMs por
segundo año consecutivo (2025)**. Los ataques **P2SQL** (Prompt-to-SQL
injection) están documentados contra frameworks populares: un usuario
formula una pregunta en lenguaje natural que induce al LLM a generar SQL
destructivo o de exfiltración, que el framework ejecuta. Como el SQL malo
aparece en la **salida** del LLM (no en el input del usuario), pasa
cualquier sanitización de entrada. En junio 2025, **EchoLeak** fue el
primer 0-click prompt injection que exfiltró datos en producción
(Microsoft 365 Copilot). Dar SQL libre a un LLM con datos de clientes
externos es indefendible.

### Por qué se descartó B (el enfoque del proyecto de referencia)

Se auditó en detalle. Da al LLM una tool `execute_safe_sql(sql)` con SQL
libre, defendida por un validador AST (sqlglot) + row cap del pool +
filtros pre-LLM. La auditoría encontró **bypasses concretos y explotables**:

- **CTEs con `ROW_NUMBER()`**: el `LIMIT` inyectado se evade con filtros
  internos `WHERE rn <= 500`.
- **UNION ALL con sub-LIMITs por rama**: dos `SELECT TOP 50` devuelven 100
  filas en una query "válida".
- **Lateral joins (Postgres)**: cada fila exterior dispara un lateral con
  su propio LIMIT → multiplicación de filas.
- **Paginación multi-turno**: turno 1 `OFFSET 0`, turno 2 `OFFSET 50`… sin
  rate-limit de sesión → extracción masiva en N turnos.
- **Agregaciones que filtran distribuciones**: `GROUP BY SUBSTRING(cedula,
  1, 3)` revela estructura PII sin violar el row cap.
- **Filtro exfil por regex**: evadible con sinonimia, spanglish, typos.

Conclusión de la auditoría: **el validador es una lista negra de bypasses
conocidos**; siempre hay uno nuevo. No es defensa en profundidad — el LLM
sigue siendo la fuente de decisión y el validador solo "espera" atajarlo.
Defensa por lista negra = se pierde por definición.

### Por qué D + E y no solo E

Las **tools curadas (E)** son lo más seguro pero tienen un techo real: si
el usuario pregunta algo que no tiene tool, *"hasta ahí llegó"*. Una tool
cubre **una pregunta**. No escala al long-tail de preguntas imprevistas.

El **semantic layer (D)** mueve el techo: una entidad modelada cubre
**cientos de preguntas** (cualquier combinación de sus métricas ×
dimensiones × filtros). Es el approach que validó la industria para
exactamente este problema (Snowflake Cortex Analyst, dbt Semantic Layer,
Cube.dev, LinkedIn QueryGPT). En el benchmark 2026 de dbt, el semantic
layer alcanza ~100% de exactitud en queries cubiertas vs 60-80% de
text-to-SQL puro.

La combinación **E + D** da lo mejor de ambos: tools curadas para lo
frecuente con formato perfecto, query semántico para el long-tail.

---

## 3. El diseño elegido: tres niveles

### Nivel 1 — Tools curadas

Tools MCP específicas para las preguntas más frecuentes y puntuales. SQL
**hardcoded y parametrizado** dentro de la tool. Ejemplos:

- `info_empresa()` — datos de la empresa (ya implementada).
- `consultar_factura(numero)` — una factura por número exacto.
- `buscar_tercero(query)` — encuentra un cliente/proveedor (máx N matches).

Ventaja: formato de salida impecable, latencia mínima, cero ambigüedad.
Uso: el 20% de preguntas que representan el 80% del tráfico.

### Nivel 2 — Query semántico (el núcleo)

Una tool `consultar_datos(query)` donde el LLM **no escribe SQL**: arma un
**objeto de consulta estructurado** (JSON) y un **compilador
determinístico que escribimos nosotros** lo traduce a SQL parametrizado.

#### Esquema del objeto de consulta

```jsonc
{
  "entidad": "ventas",                    // del catálogo semántico
  "modo": "agregado",                     // "agregado" | "detalle" | "registro"
  "metricas": ["monto_total", "cantidad"],// solo en modo agregado
  "dimensiones": ["producto"],            // agrupar por (modo agregado)
  "campos": ["numero", "fecha", "total"], // columnas (modo detalle/registro)
  "filtros": [
    {"campo": "cliente", "op": "=", "valor": "<id>"},
    {"campo": "fecha", "op": "entre", "valor": ["2026-03-01", "2026-03-31"]}
  ],
  "orden": {"campo": "monto_total", "dir": "desc"},
  "limite": 20                            // tope duro aplicado por el compilador
}
```

#### Tres modos de consulta

| Modo | Qué devuelve | Tope de filas | Caso de uso |
|------|--------------|---------------|-------------|
| `agregado` | Métricas agrupadas por dimensiones (SUM, COUNT, AVG…) | El nº de grupos (acotado por dimensión) | "ventas del mes por producto" |
| `detalle` | Filas individuales de campos permitidos | **30 (tope duro)** | "las últimas facturas de este cliente" |
| `registro` | Un único registro por filtro único (PK) | 1 | "la factura número 1234" |

> **Sobre el modo `detalle` y el tope de 30**: el cliente pidió
> explícitamente poder listar datos, no solo agregados. El modo `detalle`
> lo permite, pero con un **tope duro de 30 filas** aplicado por el
> compilador (no parametrizable por el LLM ni el usuario). 30 cubre el
> caso legítimo ("muéstrame las últimas facturas", "los productos de esta
> categoría") sin habilitar extracción masiva. Si el usuario pide más,
> SAVI responde: *"Puedo mostrarte hasta 30 a la vez; si buscas algo
> puntual dime el criterio (cliente, fecha, producto)."*

#### Qué valida el compilador (la seguridad vive acá, no en el LLM)

1. **`entidad` ∈ catálogo semántico**. Si no existe, rechaza.
2. **`metricas`/`dimensiones`/`campos`/`filtros` ∈ definición de esa
   entidad**. El LLM solo puede nombrar lo que el modelo declara. No puede
   inventar columnas ni tablas.
3. **`limite` ≤ tope del modo** (30 en detalle, 1 en registro). El LLM
   puede pedir menos, nunca más.
4. **Filtros invariables forzados** según la entidad (ej. `anulada =
   false` siempre en ventas — ver DB_MAP).
5. **Sin `OFFSET` arbitrario**: no hay paginación controlada por el
   usuario. (La paginación, si se necesita, será un cursor server-side
   acotado, no `OFFSET` libre.)
6. **SQL 100% parametrizado** con bind params de SQLAlchemy. Cero
   concatenación de strings. Imposible inyección.
7. **Campos sensibles bloqueados a nivel de modelo**: el catálogo nunca
   expone cédulas completas, tokens, passwords, columnas internas.

El LLM nunca ve un nombre de tabla, ni una columna técnica, ni escribe
SQL. Solo conoce el **vocabulario de negocio** declarado en el modelo
semántico.

#### Por qué no se puede pedir "100 registros crudos"

El LLM no tiene forma de **expresar** eso. No hay un modo "dump". Solo
puede pedir:
- agregados (devuelven totales, no filas crudas),
- detalle acotado a 30,
- un registro único.

No existe el vocabulario para "todas las filas de la tabla X". Comparado
con SQL libre, donde `SELECT * FROM ventas` es trivial de escribir, acá
es **inexpresable**.

### Nivel 3 — Modelo semántico extensible

Las entidades del ERP (ventas, terceros, productos, inventario, cartera,
compras…) se definen en archivos de configuración (un módulo Python
tipado o YAML) con sus métricas, dimensiones, filtros y mapeo a tablas.

Agregar cobertura = agregar/editar una definición de entidad, **sin tocar
el LLM ni el compilador**. El "hasta ahí llegó" se mueve de "no tengo esa
tool" a "esa entidad aún no está modelada" — y modelar una entidad cubre
cientos de preguntas.

---

## 4. Modelo semántico inicial (Wave 1)

Basado en la data real de `farmacias_similares` (ver [`DB_MAP.md`](DB_MAP.md)).
**Hallazgo crítico**: en este ERP las ventas son `CuentaCobrar.Factura` +
`DetalleFactura`, NO el schema `Venta`.

| Entidad | Tablas base | Métricas | Dimensiones | Filtro invariable |
|---------|-------------|----------|-------------|-------------------|
| **ventas** | `CuentaCobrar.Factura` + `DetalleFactura` | monto_total, cantidad_facturas, ticket_promedio, iva_total, descuento_total, unidades | periodo (día/mes/año), sucursal, cliente, producto | `anulada = false` |
| **terceros** | `Tercero.Tercero` | total_comprado, num_facturas, ultima_compra, saldo_cartera | nombre, tipo (cliente/proveedor) | — |
| **productos** | `Inventario.Producto` + `SaldoInventario` | stock_actual, unidades_vendidas, ingresos, costo_promedio | codigo, grupo, sucursal | (excluir códigos de servicio `COS*`/`COI*` cuando aplique stock físico) |
| **cartera** | `Cartera.FacturaTercero` | saldo_total, saldo_vencido, num_pendientes, dias_mora | tercero, sucursal, vencido/vigente, tipo (CxC/CxP) | separar CxC de CxP por `tipoDocumento` |
| **compras** | `CuentaPagar.FacturaCompra` + `DetalleFacturaCompra` | monto_total, num_ordenes, unidades | periodo, proveedor, producto | — |

> **Gotchas de la data** (de DB_MAP, deben codificarse en el modelo):
> - Cartera: ~99.5% del saldo aparece vencido — probablemente CxP a
>   proveedores. **Separar CxC de CxP por `tipoDocumento`** o el dato
>   engaña.
> - Productos `COS*`/`COI*` son servicios/publicidad, no inventario
>   físico (stock de 6 dígitos). Filtrarlos en métricas de stock.
> - `nombreComercial` puede ser `''` → usar `NULLIF` siempre.

---

## 5. Defensa en profundidad

Ninguna capa es la única defensa. Se suman:

| Capa | Mecanismo | Estado |
|------|-----------|--------|
| 1. Pool readonly del ERP | `default_transaction_read_only=on` + `statement_timeout=60s` | ✅ implementado |
| 2. Sin SQL libre | El LLM nunca genera SQL — solo objetos de consulta validados | Por implementar (Nivel 2) |
| 3. `allowed_tools` whitelist | Solo tools del catálogo + `consultar_datos`. Sin MCP genérico | ✅ patrón existente |
| 4. Compilador determinístico | Valida entidad/campos/límites/filtros invariables antes de generar SQL | Por implementar |
| 5. Topes de filas por modo | agregado (nº grupos), detalle (30), registro (1) | Por implementar |
| 6. Texto de BD ≠ instrucción | Las salidas de tools son `content` para el LLM, jamás interpretadas como prompt (mitiga injection vía datos: un cliente llamado "ignore previous instructions" es solo un dato) | Por diseño |
| 7. Audit log por consulta | Usuario, entidad, modo, filtros, nº filas devueltas, latencia | Por implementar |
| 8. Rate limit por usuario | N consultas/min, M filas/sesión — frena el scraping multi-turno | Por implementar |
| 9. Sin nombres técnicos en salida | "razón social", no `razonSocial`; "factura 1234", no `idFactura` | Por diseño |
| 10. Permisos por dominio (futuro) | Cuando entre auth: gating de entidades por área (ventas/stock/cartera) | Futuro |

### Sobre la paginación multi-turno (el ataque que rompió a la referencia)

Sin `OFFSET` libre + rate limit por sesión + audit con alertas de patrón,
el scraping "dame los siguientes 30, ahora los siguientes 30…" se vuelve
caro y detectable. No es 100% imposible, pero deja de ser trivial y queda
registrado. Para un producto con usuarios autenticados (cuando entre
auth), el costo reputacional + el límite por sesión lo hacen impráctico.

---

## 6. Roadmap de implementación

| Fase | Alcance | Esfuerzo |
|------|---------|----------|
| **F1 — Tools curadas Wave 1** | `consultar_factura`, `buscar_tercero`, `info_tercero`, `consultar_stock` (SQL hardcoded parametrizado) | ~2 días |
| **F2 — Query semántico (núcleo)** | Esquema del objeto + compilador + modelo de la entidad `ventas` + tool `consultar_datos` | ~3 días |
| **F3 — Resto del modelo semántico** | Entidades `terceros`, `productos`, `cartera`, `compras` | ~1 día/entidad |
| **F4 — Hardening** | Audit log en `agent_db`, rate limit por usuario, filtro pre-LLM de relevancia | ~1 día |
| **F5 (futuro) — semantic layer formal** | Migrar a dbt Semantic Layer / Cube.dev solo si la escala lo justifica | Diferido |

---

## 7. Fallback: si el cliente exige SQL literal

Si el requerimiento es **literalmente** "que el agente escriba SQL" y no
se acepta el query semántico, el único enfoque defensible es **C** — pero
la seguridad la pone la **base de datos**, no un validador en Python:

1. Schema `savi_readonly` con **VIEWS curadas** (datos de negocio
   joineados, nombres legibles, **sin columnas sensibles**).
2. DB user con `GRANT SELECT` **solo a esas views** — físicamente no puede
   ver las tablas raw. Aunque el LLM escriba `SELECT * FROM Empresa.Empresa`,
   Postgres lo rechaza por permisos.
3. **Row-Level Security** de Postgres si hay multi-tenancy.
4. `statement_timeout`, `work_mem` reducido, sin `OFFSET` a nivel sesión.
5. Validador AST + LLM judge como capas adicionales (no la única defensa).

Aun así, paginación multi-turno y agregaciones que filtran distribuciones
**siguen siendo posibles**. Por eso el query semántico (Nivel 2) es
estrictamente superior: misma libertad percibida, sin esos huecos.

---

## 8. Resumen de la decisión

- **Núcleo: query semántico (D)** — el LLM arma objetos de consulta, un
  compilador determinístico los traduce a SQL parametrizado. Flexible y
  seguro.
- **Complemento: tools curadas (E)** — para lo frecuente, con formato
  perfecto.
- **Modelo semántico extensible (Nivel 3)** — crecer cobertura sin tocar
  el LLM.
- **Modo `detalle` con tope de 30** — permite listar (lo que el cliente
  pidió) sin habilitar extracción masiva.
- **Nunca SQL libre** — descartado por OWASP #1 (prompt injection / P2SQL)
  y por los bypasses demostrados en la auditoría de la referencia.

### Fuentes

- OWASP Top 10 for LLM Applications 2025 — prompt injection #1.
- P2SQL injection contra LangChain SQLDatabaseChain (estudio 2025).
- EchoLeak — primer 0-click prompt injection en producción (Microsoft 365
  Copilot, jun 2025).
- dbt — Semantic Layer vs Text-to-SQL 2026 Benchmark.
- Snowflake Cortex Analyst, Cube.dev, LinkedIn QueryGPT — semantic layer
  enterprise.
- Auditoría interna del proyecto de referencia (acceso SQL del agente).
