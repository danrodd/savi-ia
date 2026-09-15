# Rol de solo lectura para SAVI en el ERP

> Guía de alta de una base de cliente. Aplica a instalaciones nuevas y a las
> que hoy usan `postgres`.
> Origen: hallazgo A2 de [`docs/revision-general.md`](../../docs/revision-general.md).

## Por qué

SAVI **solo lee** del ERP. Pero en las instalaciones medidas se conectaba con
el superusuario `postgres`, y eso cambia el alcance de cualquier error:

| Con un rol de solo lectura | Con superusuario |
|---|---|
| Un fallo del validador de SQL deja leer datos de más | Un fallo deja leer **archivos del servidor** (`pg_read_file`), los hashes de contraseñas de Postgres (`pg_shadow`) y cortar conexiones del ERP (`pg_terminate_backend`) |

El validador de SQL ya bloquea esas funciones (Fase 1 de seguridad), pero
**una sola barrera no alcanza**: el rol acotado es la segunda, y la que sigue
en pie si aparece una forma de evadir la primera.

SAVI no bloquea el alta con superusuario —hay instalaciones así y romperlas
sería peor que el riesgo—, pero al probar la conexión lo avisa.

## Qué ejecutar

En la base del cliente, **como administrador de Postgres**, una vez:

```sql
-- 1. El rol. Usá una contraseña generada, no una compartida.
CREATE ROLE savi_lectura LOGIN PASSWORD 'una-contraseña-generada';

-- 2. Conectarse a la base del ERP.
GRANT CONNECT ON DATABASE nombre_de_la_base TO savi_lectura;

-- 3. Ver los esquemas del ERP y leer sus tablas. Repetir por cada esquema
--    (Seguridad, Empresa, Venta, CuentaCobrar, Inventario, Nomina…).
GRANT USAGE ON SCHEMA "Seguridad" TO savi_lectura;
GRANT SELECT ON ALL TABLES IN SCHEMA "Seguridad" TO savi_lectura;

-- 4. Que las tablas NUEVAS también queden legibles. Sin esto, cada
--    actualización del ERP que agregue una tabla la deja invisible para SAVI.
ALTER DEFAULT PRIVILEGES IN SCHEMA "Seguridad"
  GRANT SELECT ON TABLES TO savi_lectura;
```

Para generarlo de una vez sobre todos los esquemas del ERP:

```sql
DO $$
DECLARE esquema text;
BEGIN
  FOR esquema IN
    SELECT nspname FROM pg_namespace
    WHERE nspname NOT LIKE 'pg\_%' AND nspname <> 'information_schema'
  LOOP
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO savi_lectura', esquema);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO savi_lectura', esquema);
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO savi_lectura',
      esquema
    );
  END LOOP;
END $$;
```

## Después

1. En SAVI, **Administración → Bases de datos**, editar la base y poner
   `savi_lectura` con su contraseña.
2. **Probar conexión**. Tiene que decir "Conexión exitosa" **sin** la
   advertencia de superusuario.
3. Probar un turno de chat que consulte datos (por ejemplo, ventas del mes).

## Qué NO hace falta

- **No** hace falta `GRANT` de escritura: SAVI nunca escribe en el ERP, y las
  conexiones se abren con `default_transaction_read_only=on`.
- **No** hace falta acceso a `pg_catalog`: el validador lo bloquea.
  `information_schema` sí se usa, y está disponible para cualquier rol
  (muestra solo los objetos sobre los que el rol tiene permiso).

## Verificación

Con el rol nuevo, estas consultas deben **fallar**:

```sql
SELECT pg_read_file('postgresql.conf', 0, 60);   -- permiso denegado
SELECT passwd FROM pg_shadow;                    -- permiso denegado
```

Y estas deben **funcionar**:

```sql
SELECT count(*) FROM "Seguridad"."Usuario";
SELECT column_name FROM information_schema.columns WHERE table_name = 'Factura';
```
