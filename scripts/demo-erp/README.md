# Base de demo del ERP

`generar.py` crea una base del ERP con una empresa inventada, **Rodamundo Llantas S.A.S.**, que vende llantas, rines, baterías y servicios de taller en Pereira. Sirve para mostrar SAVI en internet sin datos de ningún cliente.

## Qué toma de la base de origen y qué inventa

| Origen | Qué | Por qué es seguro |
|---|---|---|
| Base del ERP | La estructura: tablas, vistas y funciones (`pg_dump --schema-only`) | No lleva filas |
| Base del ERP | Países, departamentos y municipios | Catálogo público del DANE |
| Base del ERP | Tarifas de IVA, retenciones y líneas de impuesto | Catálogo de la DIAN |
| Base del ERP | Formularios y acciones del ERP | Son del producto, no del cliente |
| Generado | Empresa, almacenes, productos, terceros, ventas, compras, saldos, cartera y usuarios | Semilla fija `20261118` |

**Datos ficticios por construcción:**

- Los celulares son `300 555 xxxx` y los fijos `606 555 xxxx`.
- Los correos terminan en `example.com`, un dominio reservado.
- Los NIT y las cédulas son números al azar. Las marcas `RODAX`, `VIATRA` y `KORDO` también son inventadas.

**Lo que no se borra:** las funciones del ERP conservan sus comentarios, que incluyen los nombres de los programadores de SEO. Son los mismos en todas las instalaciones.

## Qué trae

| Dato | Cantidad aproximada |
|---|---|
| Productos | 151: 127 llantas, rines, baterías, accesorios y 6 servicios |
| Terceros | 467: 330 personas, 120 empresas, 9 proveedores, 6 vendedores y consumidor final |
| Facturas de venta | 5.400, de diciembre de 2024 a noviembre de 2026, con temporada alta en diciembre y a mitad de año |
| Facturas de compra | 220, con reposición mensual hasta el máximo de cada producto |
| Saldos de inventario | Uno por producto, almacén y mes; inicial + entradas − salidas = actual |
| Cartera | Por cobrar y por pagar, con clientes que pagan tarde |

Algunos productos dejan de venderse a mitad del periodo. Son los que SAVI muestra como inventario sin movimiento.

Contabilidad, nómina y los demás módulos quedan vacíos.

## Usuarios

Todos tienen la clave `Demo2026`.

| Usuario | Perfil | Para mostrar |
|---|---|---|
| `DEMO` | Administrador | Todo, incluidos los datos de contacto y la administración |
| `GERENTE` | Ventas, compras, inventario, cartera y terceros | Un usuario completo sin administración |
| `VENDEDOR` | Ventas e inventario, sin el módulo Terceros | Que SAVI oculta los datos de contacto sin el permiso |

## Uso

Desde la raíz del monorepo, con el entorno del backend. La conexión sale de las variables estándar de libpq:

```bash
PGHOST=localhost PGPORT=5433 PGUSER=postgres PGPASSWORD=... \
uv run --project backend python scripts/demo-erp/generar.py \
    --source <base del ERP> --target savi_demo_erp \
    --pg-bin "C:/Program Files/PostgreSQL/16/bin" --replace \
    --dump savi_demo_erp.dump
```

- `--source` es cualquier base del ERP. De ella solo se toman la estructura y los catálogos.
- `--target` tiene que contener `demo`. Así `--replace` no puede borrar por error la base de un cliente.
- `--dump` deja un volcado en formato `pg_restore`, de unos 8 MB, para cargarlo en otro servidor.

Dos corridas con la misma base de origen dan exactamente los mismos datos.

## Cargar el volcado en otro servidor

```bash
createdb -U postgres savi_demo_erp
pg_restore -U postgres --no-owner -d savi_demo_erp savi_demo_erp.dump
```

Después, en SAVI: **Administración → Bases de datos → Agregar**, con esa base y un usuario de solo lectura.
