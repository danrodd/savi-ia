"""Entidad de inventario: existencias actuales por producto y almacén.

Tablas `Inventario.SaldoInventario` + `Producto` + `Almacen` (ver
docs/DB_MAP.md §2.3). Validado contra las tres bases (farmacias, frami,
sur_andina), que tienen el mismo esquema.

POR QUÉ ESTA ENTIDAD EXISTE
---------------------------
Sin ella, "¿cuántas unidades hay de X?" iba a `consultar_libre`: solo para
administradores y con un SQL que cada modelo escribía a su manera. Un
bodeguero o un vendedor no podía preguntar por existencias.

EL STOCK ACTUAL ES EL ÚLTIMO SALDO DE CADA PRODUCTO EN CADA ALMACÉN
--------------------------------------------------------------------
`SaldoInventario` NO tiene una fila por mes para cada producto: el ERP solo
escribe el mes en que hubo movimiento. Medido el 2026-09-28:

| Base       | Pares producto-almacén | Con su último saldo en un mes anterior |
|------------|------------------------|----------------------------------------|
| sur_andina | 11.435                 | 10.088 (88 %)                          |
| frami      | 7.421                  | 5.568 (75 %)                           |
| farmacias  | 316.676                | 1.840 (1 %)                            |

Tomar "el último mes" (lo que sugería DB_MAP) deja afuera casi todo el
inventario de sur_andina y frami. Por eso la base es el último registro de
cada par, con el índice único `(idProducto, idAlmacen, anio, mes)` presente
en las tres bases.

POR QUÉ `JOIN LATERAL` Y NO UN `DISTINCT ON` SOBRE TODA LA TABLA
------------------------------------------------------------------
La primera versión calculaba el último saldo de los 316 mil pares de
farmacias y después filtraba el producto. Sola tardaba 3,9 s, pero con el
filtro por nombre Postgres ordenaba los 2,7 millones de saldos antes de
filtrar y la consulta pasaba los 60 s del límite: "¿cuántas unidades hay de
acetaminofén?" terminaba en error. Con `LATERAL` se parte del producto ya
filtrado y se busca su último saldo por almacén con el índice. Medido en
farmacias: buscar un producto, 0,05 s (antes, más de 60 s); el inventario
completo sin filtro, 17,7 s (antes, 3,9 s). Lo común es preguntar por un
producto; frami y sur_andina quedan por debajo de 1 s en los dos casos.

SERVICIOS AFUERA
----------------
`Producto.tipo = 1` son servicios ("SERVICIO DE CORTE", "MONTAJE DE
LLANTAS", "REPARACION MOTOR") y `tipo = 0` lo inventariable. En sur_andina
un servicio figuraba con 38 unidades de "stock": sin el filtro aparecía en
los rankings.

LO QUE NO SE PUEDE SEPARAR
--------------------------
En farmacias, material publicitario y volantes están cargados como productos
inventariables (tipo 0) con cientos de miles de unidades. Son productos
reales del ERP y no hay un campo que los distinga: aparecen en los rankings
por unidades. Filtrar por grupo o por nombre los deja afuera.

Hay saldos negativos (1.278 pares en farmacias): se muestran tal cual, son
un dato del ERP que el usuario puede querer ver.
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import (
    DimensionDef,
    FieldDef,
    FilterDef,
    JoinDef,
    MetricDef,
    SemanticEntity,
)
from app.modules.data_query.domain.semantic_query import FilterOp

_NUMBER_OPS = (FilterOp.GT, FilterOp.GTE, FilterOp.LT, FilterOp.LTE, FilterOp.EQ)

# Cada producto con el último saldo de cada uno de sus almacenes. Parte del
# producto para que los filtros por nombre se apliquen ANTES de buscar saldos
# (ver arriba). El filtro de servicios vive en `Producto.tipo`.
_LATEST_STOCK = """"Inventario"."Producto" p
JOIN LATERAL (
    SELECT DISTINCT ON (si."idAlmacen")
        si."idProducto", si."idAlmacen", si."cantidadActual", si."cantidadMinima",
        si."cantidadMaxima", si."costoPromedio", si."anio", si."mes"
    FROM "Inventario"."SaldoInventario" si
    WHERE si."idProducto" = p."idProducto"
    ORDER BY si."idAlmacen", si."anio" DESC, si."mes" DESC
) s ON true"""

_BAJO_MINIMO = '(s."cantidadMinima" > 0 AND s."cantidadActual" < s."cantidadMinima")'


INVENTARIO = SemanticEntity(
    name="inventario",
    base_table=_LATEST_STOCK,
    base_filters=('p."tipo" = 0',),
    required_modules=("INVENTARIO",),
    description=(
        "Existencias ACTUALES por producto y sucursal/bodega (el último saldo de "
        "cada producto en cada almacén; no incluye servicios). Úsala para "
        "'¿cuántas unidades hay de X?', '¿qué tiene la sucursal Y?', 'productos "
        "bajo el mínimo' y 'valor del inventario'. Para buscar un producto usá "
        "el filtro 'producto' con 1 o 2 palabras clave del nombre (ej. "
        "'acetaminofen 500'), sin la presentación ni unidades: TODAS las palabras "
        "tienen que aparecer. Si no encuentra nada, probá con menos palabras "
        "antes de decir que no existe. Es una foto del stock de hoy: no tiene "
        "historia por fechas."
    ),
    joins={
        "almacen": JoinDef(
            "almacen",
            'JOIN "Inventario"."Almacen" a ON a."idAlmacen" = s."idAlmacen"',
        ),
        "grupo": JoinDef(
            "grupo",
            'LEFT JOIN "Inventario"."Grupo" g ON g."idGrupo" = p."idGrupo"',
        ),
    },
    metrics={
        "unidades": MetricDef("unidades", 'SUM(s."cantidadActual")', "Unidades en existencia"),
        "productos_con_existencia": MetricDef(
            "productos_con_existencia",
            'COUNT(DISTINCT s."idProducto") FILTER (WHERE s."cantidadActual" > 0)',
            "Productos con existencia",
        ),
        "productos_bajo_minimo": MetricDef(
            "productos_bajo_minimo",
            f'COUNT(DISTINCT s."idProducto") FILTER (WHERE {_BAJO_MINIMO})',
            "Productos bajo el mínimo",
        ),
        "valor_inventario": MetricDef(
            "valor_inventario",
            'SUM(s."cantidadActual" * s."costoPromedio") FILTER (WHERE s."cantidadActual" > 0)',
            "Valor del inventario (costo promedio)",
        ),
    },
    dimensions={
        "producto": DimensionDef("producto", 'p."descripcion"', "Producto"),
        "sucursal": DimensionDef(
            "sucursal", 'a."descripcion"', "Sucursal / bodega", requires=("almacen",)
        ),
        "grupo": DimensionDef("grupo", 'g."descripcion"', "Grupo", requires=("grupo",)),
    },
    fields={
        "producto": FieldDef("producto", 'p."descripcion"', "Producto"),
        "codigo": FieldDef("codigo", 'p."codigo"', "Código"),
        "referencia": FieldDef("referencia", 'p."referencia"', "Referencia"),
        "sucursal": FieldDef(
            "sucursal", 'a."descripcion"', "Sucursal / bodega", requires=("almacen",)
        ),
        "existencia": FieldDef("existencia", 's."cantidadActual"', "Existencia"),
        "minimo": FieldDef("minimo", 's."cantidadMinima"', "Mínimo"),
        "maximo": FieldDef("maximo", 's."cantidadMaxima"', "Máximo"),
        "costo_promedio": FieldDef("costo_promedio", 's."costoPromedio"', "Costo promedio"),
        "ultimo_movimiento": FieldDef(
            "ultimo_movimiento",
            'MAKE_DATE(s."anio", s."mes", 1)',
            "Mes del último movimiento",
        ),
    },
    filters={
        # Por palabras: "tornillo 6" encuentra "TORNILLO MAD 6 * 2".
        "producto": FilterDef("producto", 'p."descripcion"', (FilterOp.CONTAINS,)),
        "codigo": FilterDef("codigo", 'p."codigo"', (FilterOp.EQ,)),
        "producto_id": FilterDef(
            "producto_id",
            's."idProducto"',
            (FilterOp.EQ, FilterOp.IN),
            value_type="number",
        ),
        "sucursal": FilterDef(
            "sucursal", 'a."descripcion"', (FilterOp.CONTAINS,), requires=("almacen",)
        ),
        "grupo": FilterDef("grupo", 'g."descripcion"', (FilterOp.CONTAINS,), requires=("grupo",)),
        "existencia": FilterDef(
            "existencia", 's."cantidadActual"', _NUMBER_OPS, value_type="number"
        ),
        "bajo_minimo": FilterDef("bajo_minimo", _BAJO_MINIMO, (FilterOp.EQ,), value_type="bool"),
        "fuera_catalogo": FilterDef(
            "fuera_catalogo", 'p."fueraCatalogo"', (FilterOp.EQ,), value_type="bool"
        ),
        "activo": FilterDef("activo", 'p."estado"', (FilterOp.EQ,), value_type="bool"),
    },
)
