# Vacíos del catálogo: rutina mensual

**Para qué:** que el catálogo de datos crezca con lo que los clientes preguntan de verdad, no con lo que se nos ocurre. Es la fase 4 de la cobertura del ERP (`odd/tasks/cobertura-erp.md`). El catálogo es lo que usa `consultar_datos`, con reglas del negocio probadas.

**Cuándo:** la primera semana de cada mes, sobre el mes anterior.

**Quién:** soporte arma la lista y desarrollo suma las entidades.

## Qué es un vacío

Una pregunta que el catálogo no alcanzó a responder. SAVI deja tres señales:

| Señal | Qué pasó | Qué suele significar |
|---|---|---|
| Resuelta con consulta libre | SAVI escribió el SQL él mismo | El tema no está en el catálogo |
| Consulta fallida | El SQL libre se rechazó o falló | El modelo no conoce esas tablas |
| Llegó al tope de consultas | El turno gastó el cupo de consultas al ERP | Un informe que el catálogo no arma en una sola consulta |

Las respuestas que no se completaron no son vacíos del catálogo: están en **Administración → Turnos fallidos**.

## Dónde mirar

**1. Cloud, entre todos los clientes:** **Resumen → Lo que le falta al catálogo.**
- Las tablas del ERP que se pidieron por SQL libre, ordenadas primero por cuántos clientes las piden.
- Solo llegan los nombres `Esquema.Tabla`: las preguntas no salen de las instalaciones.
- Viene del campo `tables` del evento `free_query/1`. Las instalaciones anteriores a ese cambio no lo mandan.

**2. En cada cliente:** **Administración → Vacíos del catálogo.**
- Cada pregunta, con lo que pasó, cuántas veces, la última vez y las tablas que tocó.
- Por defecto muestra los últimos 30 días. Se exporta a CSV.
- La ve el administrador de la empresa, y solo con los datos de su base.

## Paso a paso

1. **Ranking en Cloud.**
   - Abrir el Resumen con el periodo del mes anterior y anotar las 5 a 10 primeras tablas.
   - Si una tabla aparece en 2 o más clientes, ya es candidata.
2. **Preguntas reales.**
   - Pedirle a cada cliente con más uso el CSV de **Vacíos del catálogo** del mes. Lo exporta su administrador.
   - Las preguntas dicen qué se quería saber; las tablas solas no.
3. **Agrupar por tema.**
   - Juntar las preguntas que piden lo mismo: "anticipos de un tercero", "IVA por tarifa en compras".
   - Para cada tema, anotar las tablas, cuántos clientes y un ejemplo de pregunta tal como la escribieron.
4. **Elegir.**
   - Pasan al catálogo los temas que piden más clientes y los que fallan; un fallo pesa más que una consulta libre que salió bien.
   - Lo que pide un solo cliente puede esperar.
5. **Sumar al catálogo.** Se repite lo de la fase 2:
   - entidad o campos nuevos en `backend/app/modules/data_query/infrastructure/catalog/`;
   - su línea en "Qué datos puedes consultar" del prompt;
   - pruebas contra las bases reales en `test_catalog_against_real_erp.py`.
6. **Cerrar el ciclo.**
   - Al mes siguiente, la tabla debería bajar en el ranking. Si no baja, el modelo no está usando la entidad: revisar la descripción y el prompt.

## Qué no hacer

- **No pedir capturas ni conversaciones completas a los clientes:** el CSV ya trae la pregunta y las tablas.
- **No sumar una entidad solo porque una tabla aparece mucho.**
  - Si son consultas de exploración, como buscar columnas, la tabla no es el vacío.
  - Las consultas al esquema (`information_schema`) ya se excluyen, pero conviene mirar las preguntas.
- **No llevar preguntas de clientes a Cloud ni a ningún documento compartido.** Usar los temas agrupados del paso 3, sin nombres ni cifras.

## Referencias

- Plan y evidencia: `odd/tasks/vacios-catalogo.md`.
- Contrato: `contracts/sync/v1/README.md`, en "`free_query/1.tables`".
- Reporte local: `backend/app/modules/catalog_gaps/`.
- Ranking en Cloud: `MetricsQueries.free_query_tables` y `/console/api/catalog-gaps`.
