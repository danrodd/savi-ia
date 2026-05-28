# DB_MAP — Mapa de dominios de negocio: farmacias_similares

> **Propósito**: guía semántica para que el agente SAVI pueda responder
> preguntas de negocio sobre la BD del cliente. No es un dump del schema;
> es la capa de interpretación que mapea conceptos del negocio a tablas y
> columnas concretas.
>
> **Regla de oro**: ningún dato real de clientes, NITs, teléfonos,
> direcciones ni nombres de personas aparece en este documento.
> Los ejemplos de valores usan datos sintéticos.

---

## 1. Resumen ejecutivo

| Indicador | Valor |
|---|---|
| Total tablas | 423 |
| Tablas con datos | 140 |
| Schemas de usuario | 23 |
| Total filas (est.) | ~24 millones |
| Período cubierto | 2025-05-06 a 2026-05-06 (1 año) |
| Sucursales (almacenes) | 84 (80 activas) |
| Terceros registrados | 18,425 (16,664 clientes / 1,535 proveedores) |
| Productos registrados | 2,885 |

### Distribución de volumen por dominio

| Schema | Filas (est.) | Rol |
|---|---|---|
| Contabilidad | 11,688,885 | Libro diario y reportes contables |
| Inventario | 10,467,432 | Stock, movimientos, recálculos |
| CuentaCobrar | 1,612,530 | **Ventas reales** (facturas + detalles) |
| CuentaPagar | 61,213 | Compras a proveedores |
| Cartera | 30,937 | Cuentas por cobrar y pagar (saldos) |
| Tercero | 18,684 | Clientes y proveedores |
| Seguridad | 21,634 | Usuarios, permisos |
| General | 2,122 | Catálogos (documentos, etc.) |

### Hallazgo crítico — dónde viven las ventas

El schema `Venta` tiene **12 filas** y está deshabilitado para este cliente.
Las ventas reales están en:

```
CuentaCobrar.Factura      → 458,993 facturas vigentes
CuentaCobrar.DetalleFactura → 966,944 líneas de venta
```

Cualquier pregunta sobre "ventas", "facturación", "ingresos" o "tickets"
debe resolverse con `CuentaCobrar.Factura` + `CuentaCobrar.DetalleFactura`,
**no** con el schema `Venta`.

---

## 2. Mapa por dominio de negocio

---

### 2.1 Ventas / Facturación

**Qué representa**: cada transacción de venta al cliente final.
Cubre facturas electrónicas, notas crédito y notas débito emitidas
desde las cajas de cada sucursal.

#### Tablas clave

| Tabla | Rol | Filas (est.) |
|---|---|---|
| `CuentaCobrar.Factura` | Cabecera de la venta | 458,996 |
| `CuentaCobrar.DetalleFactura` | Líneas (productos) de cada venta | 967,601 |
| `CuentaCobrar.FacturaIva` | Desglose de IVA por tarifa | 180,117 |
| `CuentaCobrar.FacturaElectronica` | Metadata DIAN (CUFE, UUID, estado FE) | 3,441 |
| `CuentaCobrar.FacturaDevolucion` | Notas crédito / devoluciones | 910 |
| `CuentaCobrar.FacturaIndicadorRetencion` | Retenciones por factura | 885 |

#### Columnas relevantes — `CuentaCobrar.Factura`

| Columna | Tipo | Semántica |
|---|---|---|
| `idFactura` | bigint | PK |
| `idDocumento` | integer | Tipo de documento (FK → `General.Documento`) |
| `numero` | bigint | Número consecutivo de la factura |
| `fecha` | timestamptz | Fecha/hora de emisión |
| `fechaVencimiento` | timestamptz | Vencimiento (crédito) |
| `idTercero` | bigint | Cliente (FK → `Tercero.Tercero`) |
| `idCentroCosto` | integer | Sucursal / caja |
| `idTurnoCaja` | bigint | Turno de caja (FK → tabla de turnos) |
| `subtotal` | numeric | Subtotal antes de impuestos |
| `descuento` | numeric | Descuento total aplicado |
| `valorGravadoIva` | numeric | Base gravada con IVA |
| `valorExcluidoIva` | numeric | Base excluida de IVA |
| `valorImpuestoIva` | numeric | Valor del IVA |
| `totalIpoConsumo` | numeric | Impuesto al consumo (medicamentos sin IVA) |
| `total` | numeric | Total a pagar |
| `anulada` | boolean | Si la factura fue anulada |
| `tipoCartera` | integer | Tipo de cartera (0 = normal) |
| `idFormaPago` | integer | Forma de pago (efectivo, tarjeta, mixto) |
| `valorPagoEfectivo` | numeric | Pago en efectivo |
| `valorPagoTarjeta` | numeric | Pago con tarjeta |

#### Columnas relevantes — `CuentaCobrar.DetalleFactura`

| Columna | Tipo | Semántica |
|---|---|---|
| `idDetalleFactura` | bigint | PK |
| `idFactura` | bigint | FK → `CuentaCobrar.Factura` |
| `idProducto` | bigint | FK → `Inventario.Producto` |
| `idAlmacen` | integer | FK → `Inventario.Almacen` (sucursal) |
| `cantidad` | numeric | Unidades vendidas |
| `valorUnitario` | numeric | Precio unitario de venta |
| `costo` | numeric | Costo del producto al momento de la venta |
| `porcentajeDescuento` | numeric | % de descuento aplicado |
| `valorDescuento` | numeric | Valor del descuento |
| `porcentajeIva` | numeric | Tasa de IVA (0, 5, 19) |
| `valorIva` | numeric | Valor del IVA en la línea |
| `total` | numeric | Total de la línea (cantidad × precio - descuento) |
| `obsequio` | boolean | Si el ítem fue entregado como obsequio |
| `lote` | varchar | Número de lote del medicamento |
| `fechaVencimientoLote` | timestamptz | Vencimiento del lote |

#### Estadísticas del período

| Métrica | Valor |
|---|---|
| Período | 2025-05-06 → 2026-05-06 |
| Facturas vigentes | 458,993 |
| Facturas anuladas | 3 |
| Total facturado acumulado | ~$21,676 M COP |
| Ticket promedio | ~$47,227 COP |
| Clientes distintos facturados | 16,691 |
| Productos distintos vendidos | 1,096 |
| Líneas de venta | 966,944 |
| IVA total | ~$1,328 M COP |
| Descuentos totales | ~$2,231 M COP |
| Ítems de obsequio | 12,675 líneas |

#### Tipos de documento (idDocumento → General.Documento)

Todos los documentos en `CuentaCobrar.Factura` tienen `tipo = 2`
(Factura de Venta Electrónica). Hay ~30 documentos distintos, cada uno
correspondiente a una caja de una sucursal específica
(ej. "FACTURA DE VENTA ELECTRÓNICA CANDELARIA CAJA 1").

#### Relaciones

```
General.Documento (idDocumento)
         ↑
CuentaCobrar.Factura (idFactura)
    ├── idTercero → Tercero.Tercero
    ├── idCentroCosto → [catálogo centros de costo]
    └── idTurnoCaja → [turno de caja]
         ↓
CuentaCobrar.DetalleFactura (idDetalleFactura)
    ├── idProducto → Inventario.Producto
    └── idAlmacen  → Inventario.Almacen
```

---

### 2.2 Terceros (Clientes y Proveedores)

**Qué representa**: toda persona natural o jurídica con la que
la empresa tiene relación comercial. Una misma entidad puede ser
cliente, proveedor y/o empleado simultáneamente.

#### Tabla clave

| Tabla | Rol | Filas (est.) |
|---|---|---|
| `Tercero.Tercero` | Directorio único de terceros | 18,425 |

#### Segmentación por rol

| Segmento | Filas |
|---|---|
| Solo clientes (`cliente=true`, `proveedor=false`) | 16,664 |
| Solo proveedores (`proveedor=true`, `cliente=false`) | 1,535 |
| Sin rol definido | 125 |
| Ambos (cliente y proveedor) | 101 |

#### Columnas relevantes — `Tercero.Tercero`

| Columna | Tipo | Semántica |
|---|---|---|
| `idTercero` | bigint | PK |
| `numeroIdentificacion` | varchar | NIT o cédula |
| `tipoDocumento` | integer | Tipo de doc de identidad |
| `razonSocial` | varchar | Nombre de la empresa (persona jurídica) |
| `primerNombre` + `primerApellido` | varchar | Nombre de persona natural |
| `nombreComercial` | varchar | Nombre comercial / alias |
| `cliente` | boolean | Es cliente |
| `proveedor` | boolean | Es proveedor |
| `empleado` | boolean | Es empleado |
| `activo` | boolean | Está activo en el sistema |
| `telefonoFijo` | varchar | Teléfono (dato sensible — no exponer) |
| `celular` | varchar | Celular (dato sensible — no exponer) |
| `email` | varchar | Email (dato sensible — no exponer) |
| `idPlanContable` | bigint | Cuenta contable asociada |

> **Nota para el agente**: nunca devolver `telefonoFijo`, `celular`,
> `email`, `direccion` ni `numeroIdentificacion` al usuario final.
> Solo devolver nombre comercial y datos de negocio.

---

### 2.3 Inventario / Productos

**Qué representa**: el catálogo de productos y el stock disponible
por sucursal. Incluye medicamentos, insumos, artículos publicitarios
y servicios.

#### Tablas clave

| Tabla | Rol | Filas (est.) |
|---|---|---|
| `Inventario.Producto` | Catálogo maestro de productos | 2,885 |
| `Inventario.SaldoInventario` | Stock mensual por producto y almacén | 2,699,598 |
| `Inventario.ProductoAlmacen` | Configuración producto-almacén | 215,615 |
| `Inventario.Almacen` | Catálogo de sucursales / bodegas | 84 |
| `Inventario.LogRecalculoInventario` | Historial de recálculos de stock | 3,040,636 |

#### Columnas relevantes — `Inventario.Producto`

| Columna | Tipo | Semántica |
|---|---|---|
| `idProducto` | bigint | PK |
| `codigo` | varchar | Código interno (ej. `COL0124`) |
| `codigoBarras` | varchar | Código de barras EAN |
| `descripcion` | varchar | Nombre del producto |
| `tipo` | integer | Tipo (medicamento, insumo, servicio, etc.) |
| `registroInvima` | varchar | Número de registro INVIMA |
| `codigoCum` | varchar | Código CUM del medicamento |
| `idMarca` | integer | FK → catálogo de marcas |
| `idGrupo` | integer | FK → grupo del producto |
| `idSubgrupo` | integer | Subgrupo |
| `ventaLibre` | boolean | Si se vende sin fórmula médica |
| `ventaNoLibre` | boolean | Si requiere fórmula médica |
| `presentacion` | varchar | Forma farmacéutica |
| `concentracion` | varchar | Concentración del medicamento |
| `fueraCatalogo` | boolean | Si fue descontinuado |
| `clasificacionRegistroInvima` | varchar | Clasificación regulatoria |

#### Columnas relevantes — `Inventario.SaldoInventario`

| Columna | Tipo | Semántica |
|---|---|---|
| `idSaldoInventario` | bigint | PK |
| `idProducto` | bigint | FK → `Inventario.Producto` |
| `idAlmacen` | integer | FK → `Inventario.Almacen` |
| `anio` | integer | Año del saldo |
| `mes` | integer | Mes del saldo |
| `cantidadInicial` | numeric | Stock al inicio del período |
| `cantidadEntrada` | numeric | Entradas en el período |
| `cantidadSalida` | numeric | Salidas en el período |
| `cantidadActual` | numeric | Stock disponible actual |
| `cantidadMinima` | numeric | Stock mínimo configurado |
| `cantidadMaxima` | numeric | Stock máximo configurado |
| `costoPromedio` | numeric | Costo promedio del producto |

#### Columnas — `Inventario.Almacen`

| Columna | Tipo | Semántica |
|---|---|---|
| `idAlmacen` | integer | PK |
| `codigo` | varchar | Código de la sucursal |
| `descripcion` | varchar | Nombre de la sucursal |
| `estado` | boolean | Activa/inactiva |
| `almacenPrincipal` | boolean | Si es el CEDIS / almacén central |
| `almacenEntrega` | boolean | Si hace entregas al cliente |
| `idCentroCosto` | integer | FK → centro de costo |

#### Relaciones

```
Inventario.Producto (idProducto)
    ├── idMarca → [catálogo marcas]
    ├── idGrupo → [catálogo grupos]
    │
    ├── → Inventario.SaldoInventario (idProducto + idAlmacen + anio + mes)
    │         ↳ Inventario.Almacen (idAlmacen)
    │
    ├── → Inventario.ProductoAlmacen (idProducto + idAlmacen)
    │         ↳ tabla de habilitación producto por sucursal
    │
    └── → CuentaCobrar.DetalleFactura (idProducto)
```

> **Observación**: el stock en `SaldoInventario` es acumulativo por período
> (año/mes). Para stock actual se usa el registro con el período más reciente.
> Los top 10 por stock incluyen productos de tipo "servicio" y publicidad
> con cantidades muy altas (ej. paquetes de documentos electrónicos con
> 2,475,000 unidades) — probablemente servicios facturados como unidades,
> no inventario físico. Filtrar por tipo de producto al responder consultas
> de stock de medicamentos.

---

### 2.4 Cartera

**Qué representa**: el estado de deuda de cada documento emitido.
Cubre cuentas por cobrar a clientes y cuentas por pagar a proveedores.
Es la fuente para responder "¿qué le debe el cliente X a la empresa?"
o "¿qué le debe la empresa al proveedor Y?".

#### Tablas clave

| Tabla | Rol | Filas (est.) |
|---|---|---|
| `Cartera.FacturaTercero` | Saldos de cartera por documento/cuota | 12,034 |
| `Cartera.CruceFacturaPago` | Registros de pagos aplicados a facturas | 6,556 |
| `Cartera.ReciboComprobante` | Recibos de caja (pagos del cliente) | 3,861 |
| `Cartera.DetalleReciboComprobante` | Líneas del recibo | 6,556 |

#### Columnas relevantes — `Cartera.FacturaTercero`

| Columna | Tipo | Semántica |
|---|---|---|
| `idFacturaTercero` | bigint | PK |
| `idDocumento` | integer | Tipo de documento |
| `numero` | bigint | Número consecutivo |
| `cuota` | integer | Número de cuota |
| `idTercero` | bigint | FK → `Tercero.Tercero` |
| `idCentroCosto` | integer | Sucursal |
| `fechaFactura` | timestamptz | Fecha del documento original |
| `fechaVencimientoCuota` | timestamptz | Fecha límite de pago |
| `valorDocumento` | numeric | Valor original del documento |
| `valorPagado` | numeric | Lo que se ha pagado |
| `valorSaldo` | numeric | Saldo pendiente |
| `tipoDocumento` | integer | Tipo (3=CxP, 2=CxC, etc.) |
| `idFactura` | bigint | FK → `CuentaCobrar.Factura` (si es CxC) |
| `idFacturaCompra` | bigint | FK → `CuentaPagar.FacturaCompra` (si es CxP) |
| `estadoCuentaCobro` | integer | Estado de la cuenta de cobro |

#### Estadísticas de cartera actual

| Métrica | Valor |
|---|---|
| Total documentos en cartera | 12,034 |
| Con saldo pendiente | 4,731 |
| Saldo total pendiente | ~$15,495 M COP |
| Documentos vencidos | 4,712 |
| Saldo vencido | ~$15,435 M COP |
| Período cubierto | 2025-01-01 → 2026-05-06 |

> **Observación inesperada**: casi toda la cartera con saldo pendiente
> (4,712 de 4,731 registros) aparece como vencida. Esto puede indicar
> que la mayoría corresponde a cuentas por pagar a proveedores (no
> cuentas por cobrar a clientes), o que los plazos de vencimiento
> configurados son cortos. Filtrar por `tipoDocumento` para separar
> CxC (clientes) de CxP (proveedores).

---

### 2.5 Compras / Cuentas por Pagar

**Qué representa**: las órdenes y facturas de compra a proveedores,
incluyendo el stock recibido de laboratorios y distribuidores.

#### Tablas clave

| Tabla | Rol | Filas (est.) |
|---|---|---|
| `CuentaPagar.FacturaCompra` | Facturas recibidas de proveedores | 5,353 |
| `CuentaPagar.DetalleFacturaCompra` | Líneas de la factura de compra | 16,419 |
| `CuentaPagar.OrdenCompra` | Órdenes de compra | 5,205 |
| `CuentaPagar.DetalleOrdenCompra` | Líneas de la OC | 17,188 |
| `CuentaPagar.FacturaIvaCompra` | IVA de las compras | 3,123 |
| `CuentaPagar.FacturaIndicadorRetencionCompra` | Retenciones en compras | 4,273 |

#### Columnas relevantes — `CuentaPagar.FacturaCompra`

| Columna | Tipo | Semántica |
|---|---|---|
| `idFacturaCompra` | bigint | PK |
| `idDocumento` | integer | Tipo de documento de compra |
| `numero` | bigint | Consecutivo interno |
| `referenciaFacturaProveedor` | varchar | Número de factura del proveedor |
| `idTercero` | bigint | FK → `Tercero.Tercero` (proveedor) |
| `fecha` | timestamptz | Fecha de la compra |
| `fechaVencimiento` | timestamptz | Vencimiento de la obligación |
| `subtotal` | numeric | Subtotal de la compra |
| `total` | numeric | Total de la factura de compra |
| `anulada` | boolean | Si fue anulada |

#### Estadísticas de compras

| Métrica | Valor |
|---|---|
| Período | 2025-01-01 → 2026-05-06 |
| Total facturas de compra | 5,353 |
| Total comprado acumulado | ~$22,621 M COP |
| Proveedores distintos | 393 |

---

### 2.6 Contabilidad

**Qué representa**: el libro diario del ERP. Cada transacción de
venta, compra, pago o ajuste genera asientos contables dobles en
`MovimientoContable` + `DetalleMovimientoContable`.

#### Tablas clave

| Tabla | Rol | Filas (est.) |
|---|---|---|
| `Contabilidad.MovimientoContable` | Cabecera del asiento | ~375K |
| `Contabilidad.DetalleMovimientoContable` | Líneas débito/crédito | 3,751,187 |
| `Contabilidad.RptTemBalanceGeneralPRO` | Vista temporal para balance | 3,749,201 |
| `Contabilidad.PlanContable` | Plan de cuentas | — |

> **Nota**: la contabilidad NO es el dominio principal para consultas
> de negocio del agente. El agente debe usar `CuentaCobrar`, `Inventario`
> y `CuentaPagar` para responder preguntas operativas. Contabilidad
> es útil solo para preguntas financieras avanzadas (balance, P&G).

---

## 3. Catálogo de preguntas de negocio

Las preguntas que la base de datos soporta responder:

### Ventas y facturación
- ¿Cuánto vendió la empresa en el período X? → `SUM(Factura.total)` filtrado por `fecha`
- ¿Cuáles son las ventas por sucursal? → agrupar por `idCentroCosto` o `Almacen.descripcion`
- ¿Cuáles fueron las facturas de un cliente? → filtrar `Factura` por `idTercero`
- ¿Cuáles son los productos más vendidos? → `SUM(DetalleFactura.cantidad)` agrupado por `idProducto`
- ¿Cuál es el ticket promedio de venta? → `AVG(Factura.total)` WHERE `anulada=false`
- ¿Cuántas facturas se anularon? → `COUNT(*) WHERE anulada=true`
- ¿Cuánto IVA se recaudó? → `SUM(Factura.valorImpuestoIva)`
- ¿Qué productos se regalaron como obsequio? → `DetalleFactura WHERE obsequio=true`
- ¿Cuáles fueron las ventas por forma de pago? → agrupar por `idFormaPago`

### Clientes
- ¿Quiénes son los mejores clientes por facturación? → join `Factura` + `Tercero`, agrupar por cliente
- ¿Cuántos clientes compran habitualmente? → `COUNT(DISTINCT idTercero)` por período
- ¿Cuándo compró por última vez el cliente X? → `MAX(fecha)` filtrado por `idTercero`
- ¿Cuánto ha comprado históricamente el cliente X? → `SUM(total)` filtrado por cliente

### Inventario y productos
- ¿Cuántas unidades hay de un producto? → `SUM(SaldoInventario.cantidadActual)` para `anio/mes` actual
- ¿Qué stock tiene la sucursal X de un producto? → filtrar `SaldoInventario` por `idAlmacen`
- ¿Qué productos tienen stock bajo el mínimo? → `cantidadActual < cantidadMinima`
- ¿Qué productos están fuera de catálogo? → `Producto WHERE fueraCatalogo=true`

### Cartera y cobros
- ¿Qué documentos tiene pendientes el proveedor X? → `Cartera.FacturaTercero WHERE valorSaldo>0` filtrado por `idTercero`
- ¿Cuál es la cartera vencida total? → `SUM(valorSaldo) WHERE fechaVencimientoCuota < NOW()`
- ¿Qué pagos recibió la empresa en el período X? → `Cartera.ReciboComprobante` por `fecha`

### Compras a proveedores
- ¿Cuánto se compró al proveedor X en el período Y? → `SUM(FacturaCompra.total)` filtrado por `idTercero`
- ¿Cuáles son las facturas pendientes de pago a proveedores? → `Cartera.FacturaTercero WHERE tipoDocumento=3 AND valorSaldo>0`
- ¿Qué productos se compraron en el período X? → join `DetalleOrdenCompra` + `Producto`

---

## 4. Entidades semánticas — propuesta Wave 1

Estas son las entidades que el agente debe modelar para las tools MCP
de consulta (Wave 1 del backlog).

### 4.1 Entidad: Venta

| Aspecto | Detalle |
|---|---|
| **Tabla principal** | `CuentaCobrar.Factura` |
| **Join obligatorio** | `CuentaCobrar.DetalleFactura` para desglose por producto |
| **Filtro base** | `Factura.anulada = false` |

**Métricas**

| Métrica | Expresión SQL |
|---|---|
| Total facturado | `SUM(f.total)` |
| Cantidad de facturas | `COUNT(DISTINCT f.idFactura)` |
| Ticket promedio | `AVG(f.total)` |
| IVA recaudado | `SUM(f.valorImpuestoIva)` |
| Descuentos otorgados | `SUM(d.valorDescuento)` |
| Unidades vendidas | `SUM(d.cantidad)` |
| Costo de ventas | `SUM(d.costo * d.cantidad)` |

**Dimensiones**

| Dimensión | Expresión |
|---|---|
| Período (día/mes/año) | `DATE_TRUNC('day'/'month'/'year', f.fecha)` |
| Sucursal | `a.descripcion` via `d.idAlmacen → Inventario.Almacen` |
| Cliente | `t.nombreComercial` via `f.idTercero → Tercero.Tercero` |
| Producto | `p.descripcion` via `d.idProducto → Inventario.Producto` |
| Forma de pago | `f.idFormaPago` |
| Tipo de documento | `doc.descripcion` via `f.idDocumento → General.Documento` |

**Filtros frecuentes**

- Rango de fechas: `f.fecha BETWEEN :fecha_inicio AND :fecha_fin`
- Sucursal: `d.idAlmacen = :idAlmacen` o `a.codigo = :codigo`
- Cliente: `f.idTercero = :idTercero`
- Producto: `d.idProducto = :idProducto` o `p.codigo = :codigo`
- Anuladas excluidas: `f.anulada = false` (siempre)

---

### 4.2 Entidad: Tercero (Cliente/Proveedor)

| Aspecto | Detalle |
|---|---|
| **Tabla principal** | `Tercero.Tercero` |
| **Filtro base** | `cliente=true` para clientes; `proveedor=true` para proveedores |

**Métricas**

| Métrica | Expresión |
|---|---|
| Total comprado | `SUM(Factura.total)` agrupado por `idTercero` |
| Frecuencia de compra | `COUNT(DISTINCT idFactura)` agrupado por `idTercero` |
| Última compra | `MAX(Factura.fecha)` agrupado por `idTercero` |
| Saldo pendiente | `SUM(FacturaTercero.valorSaldo)` |

**Dimensiones**

| Dimensión | Expresión |
|---|---|
| Nombre | `razonSocial` o `primerNombre + primerApellido` |
| Nombre comercial | `nombreComercial` |
| Tipo | `cliente` / `proveedor` / `empleado` (boolean flags) |

---

### 4.3 Entidad: Producto

| Aspecto | Detalle |
|---|---|
| **Tabla principal** | `Inventario.Producto` |

**Métricas**

| Métrica | Expresión |
|---|---|
| Stock actual | `SUM(SaldoInventario.cantidadActual)` para período actual |
| Stock por sucursal | filtrar por `idAlmacen` en `SaldoInventario` |
| Unidades vendidas | `SUM(DetalleFactura.cantidad)` |
| Ingresos generados | `SUM(DetalleFactura.total)` |
| Costo promedio | `SaldoInventario.costoPromedio` |

**Dimensiones**

| Dimensión | Expresión |
|---|---|
| Código | `Producto.codigo` |
| Nombre | `Producto.descripcion` |
| Grupo | `Producto.idGrupo` → catálogo de grupos |
| Requiere fórmula | `ventaNoLibre = true` |
| Estado | `fueraCatalogo` (descontinuado) |
| Sucursal | `Inventario.Almacen.descripcion` |

---

### 4.4 Entidad: Cartera

| Aspecto | Detalle |
|---|---|
| **Tabla principal** | `Cartera.FacturaTercero` |
| **Filtro CxC (clientes)** | `idFactura IS NOT NULL` o `tipoDocumento` = tipo CxC |
| **Filtro CxP (proveedores)** | `idFacturaCompra IS NOT NULL` o `tipoDocumento` = tipo CxP |

**Métricas**

| Métrica | Expresión |
|---|---|
| Saldo total | `SUM(valorSaldo)` |
| Saldo vencido | `SUM(valorSaldo) WHERE fechaVencimientoCuota < NOW()` |
| Documentos pendientes | `COUNT(*) WHERE valorSaldo > 0` |
| Días de mora | `CURRENT_DATE - fechaVencimientoCuota` (calculado) |

**Dimensiones**

| Dimensión | Expresión |
|---|---|
| Tercero | `Tercero.nombreComercial` |
| Sucursal | `idCentroCosto` |
| Vencido / vigente | `fechaVencimientoCuota < NOW()` |
| Tipo (CxC / CxP) | `tipoDocumento` |

---

## 5. Notas de implementación para el agente

### 5.1 Joins que siempre son necesarios

Para identificar el nombre del cliente de una factura:
```sql
JOIN "Tercero"."Tercero" t ON t."idTercero" = f."idTercero"
-- Usar: COALESCE(NULLIF(t."nombreComercial",''), t."razonSocial",
--               t."primerNombre" || ' ' || t."primerApellido")
```

Para identificar la sucursal de un detalle de factura:
```sql
JOIN "Inventario"."Almacen" a ON a."idAlmacen" = d."idAlmacen"
```

### 5.2 Convenciones de nombres en esta BD

- PK siempre: `id<NombreTabla>` (ej. `idFactura`, `idProducto`)
- FK siempre: `id<EntidadReferenciada>` (ej. `idTercero`, `idAlmacen`)
- Fechas de auditoría: `fechaCreacion`, `fechaModificacion` (no son de negocio)
- Borrado lógico: no existe `deleted_at` — se usa `anulada = true` o `estado = false`

### 5.3 Gotchas

- **`nombreComercial` puede ser vacío string `''`**: usar `NULLIF(nombreComercial, '')`.
- **`SaldoInventario` tiene N filas por producto** (una por almacén × mes × año). Para stock actual, filtrar por el año y mes más reciente.
- **`tipoCartera = 0` en todas las facturas** de este cliente: no es una dimensión útil para filtrar.
- **Productos con stock altísimo no son siempre físicos**: códigos `COS*` (servicios) y `COI*` (insumos/publicidad) pueden tener cantidades de 6 dígitos. Filtrar por tipo de producto o por código `COL*` para medicamentos.
- **Los documentos de factura corresponden a cajas de sucursales individuales**: el nombre del documento incluye la sucursal y número de caja. Para agrupar por sucursal real, usar `idCentroCosto` o `DetalleFactura.idAlmacen`.
- **Fechas en UTC**: todas las `timestamptz` están en UTC. Ajustar a hora colombiana (UTC-5) para reportes.
