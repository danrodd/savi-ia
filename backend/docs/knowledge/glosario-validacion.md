# Validación del glosario del ERP

> Archivo validado: `app/modules/knowledge/data/shared/glossary.json` (85 términos).
> Fecha: 2026-09-29. La revisión la hizo el equipo de SAVI, no SEO Group: se
> contrastó cada definición con la base del ERP y con fuentes oficiales.

## Cómo se validó

1. **Base del ERP.** Para los términos propios del sistema se buscaron las
   tablas que los respaldan en las tres bases (farmacias, frami, sur_andina),
   que tienen el mismo esquema.
2. **Fuentes oficiales.** Las definiciones legales y tributarias se
   contrastaron con la DIAN, el Estatuto Tributario, la Superintendencia
   Financiera, el Banco de la República, MinSalud / Fondo Nacional de
   Estupefacientes y la normativa laboral vigente en 2026.
3. **Sin cifras que vencen.** No se incluyen valores que cambian cada año
   (UVT, salario mínimo, auxilio de transporte): solo qué es cada cosa. Las
   tarifas que sí aparecen son porcentajes fijados por ley.

## Correcciones

| Término | Qué estaba mal o faltaba | Fuente |
|---|---|---|
| Factura electrónica | Decía que "tiene validez legal como título valor". Lo es cuando el comprador la acepta (expresa o tácitamente en 3 días) y, para circular, se registra en el RADIAN | [DIAN, Oficio 906781/2022](https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_906781_2022.htm) |
| RADIAN | Faltaba que solo registra facturas a crédito aceptadas | [DIAN, Oficio 906781/2022](https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_906781_2022.htm) |
| Tasa de usura | Decía que la certifica la Superfinanciera. La Superfinanciera certifica el interés bancario corriente; la usura es 1,5 veces ese interés | [Superfinanciera](https://www.superfinanciera.gov.co/preguntas-frecuentes/12/12-tasas-de-interes/), [Banco de la República](https://www.banrep.gov.co/es/glosario/tasa-usura) |
| Parafiscales | Faltaba la exoneración de SENA, ICBF y salud del empleador por trabajadores de menos de 10 salarios mínimos | [ET art. 114-1](https://estatuto.co/114-1) |
| Impuesto al consumo | Faltaba la telefonía móvil, internet y datos, uno de sus hechos generadores | [ET art. 512-1](https://estatuto.co/512-1) |
| Intereses de cesantías | Faltaba la tasa (12 % anual), la fecha (31 de enero) y el pago mensual pactado que permite la Ley 2466 de 2025 | [Buk](https://www.buk.co/blog/intereses-de-cesantias) |
| Prima de servicios | Faltaban las fechas de pago (30 de junio y 20 de diciembre) | [Buk](https://www.buk.co/blog/intereses-de-cesantias) |
| Auxilio de transporte | Decía "hasta cierto número de salarios mínimos"; son dos | Código Sustantivo del Trabajo y decreto anual |
| Microcrédito | Faltaba el tope legal: 25 salarios mínimos por deudor | [Superfinanciera](https://www.superfinanciera.gov.co/publicaciones/10084639/), Ley 590 de 2001 art. 39 |
| ReteIVA | Faltaba la tarifa general (15 % del IVA) y quiénes la practican | [DIAN](https://www.dian.gov.co/impuestos/Autorretenedores/Paginas/Agente-de-Retencion-del-Impuesto-sobre-las-Ventas.aspx) |
| AFP | Faltaba la reforma pensional: desde el 1 de abril de 2027 los aportes hasta 2,3 salarios mínimos van a Colpensiones | Ley 2381 de 2024, [Sentencia C-264 de 2026](https://www.fenalcoantioquia.com/blogs/post/corte-constitucional-reforma-pensional) |
| Medicamento de control especial | Faltaba quién lo vigila (Fondo Nacional de Estupefacientes) y el recetario oficial | [Fondo Nacional de Estupefacientes](https://fne.minsalud.gov.co/) |
| SKU | Tenía el alias "referencia", que en el ERP es otra columna de `Producto` (la referencia del proveedor): se quitó y se aclaró que el SKU es el código | Base del ERP, `Inventario.Producto` |

## Términos nuevos (respaldados por la base del ERP)

| Término | Dónde aparece en el ERP |
|---|---|
| Impuestos saludables, ICUI, IBUA | `CuentaCobrar.FacturaImpuestoSaludable`, `CuentaPagar.FacturaCompraImpuestoSaludable`; en farmacias el indicador "IMPUESTO ICUI" al 20 %, la tarifa de ley para 2025 ([DIAN](https://www.dian.gov.co/aduanas/Paginas/Impuestos-Saludables.aspx)) |
| Cartera financiera | Módulo `CarteraFinanciera` (créditos, cuotas, cupos, pagos) |
| Deudor solidario | `CarteraFinanciera.DeudorSolidarioCredito` |
| Prórroga | `CarteraFinanciera.ProrrogaCuotaCreditoAsociado` |
| Cotización | `Venta.Cotizacion*` |
| Forma farmacéutica | `Inventario.FormaFarmaceutica` |

## Términos del ERP confirmados en la base

Remisión (`CuentaCobrar.Remision`), orden de compra (`CuentaPagar.OrdenCompra`,
`AutorizaOrdenCompra`), documento soporte (`CuentaPagar.DocumentoSoporte`),
factura electrónica, nota crédito y nota débito (`CuentaCobrar.FacturaElectronica`,
`MotivoNotaCredito`, `FacturaNotaDebito`), resolución de facturación
(`General.Resolucion`), centro de costo (`Empresa.CentroCosto`), PUC y exógena
(`Contabilidad.PlanContable`, `RptExogena1001`), PILA y nómina electrónica
(`Nomina.LiquidacionPila`, `DocumentoNominaElectronica`), retención en la fuente
(`Nomina.TablaRetencionFuente`), toma física y lote (`Inventario.ConteoTomaFisica`,
`SaldoInventarioLote`), amortización (`CuentaCobrar.AmortizacionCredito`), orden
de trabajo (`Mantenimiento.OrdenTrabajo`), recibo de caja
(`Cartera.ReciboComprobante`), impuesto al consumo (columnas `ipoConsumo`).

## Sin cambios

El resto de las definiciones (DIAN, NIT, DV, RUT, IVA, exento, excluido,
retención en la fuente, ReteICA, ICA, UVT, CUFE, CUDE, nota crédito y débito,
documento soporte, resolución de facturación, régimen simple, responsable de
IVA, gran contribuyente, autorretenedor, exógena, PUC, NIIF, centro de costo,
CxC, CxP, cartera, comprobante de egreso, recibo de caja, conciliación
bancaria, balance general, estado de resultados, costo promedio, activo fijo,
depreciación, PILA, EPS, ARL, caja de compensación, cesantías, SMMLV, nómina
electrónica, EAN, stock mínimo, toma física, kardex, orden de compra, remisión,
CEDIS, lote, INVIMA, registro sanitario, CUM, venta libre, fórmula médica,
RIPS, IPS, SOAT, RTM, orden de trabajo, mora, centrales de riesgo y
amortización) se revisaron sin encontrar errores y se mantienen. A diferencia
de las correcciones de arriba, no se contrastó cada una contra una fuente
citada: son definiciones estables y de uso general. Los términos propios del
ERP sí se confirmaron en la base (sección anterior).

## Cuándo revisarlo de nuevo

- Cuando entre en vigencia la reforma pensional (1 de abril de 2027): AFP,
  Colpensiones y PILA.
- Cuando cambien por ley las tarifas que se mencionan (ReteIVA 15 %,
  parafiscales, ICUI).
