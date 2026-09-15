# Fase 1 — Datos del ERP

> Objetivo: que un usuario solo pueda consultar los datos que le corresponden,
> y que el SQL generado por la IA no pueda usar el motor como superusuario.
> Esfuerzo estimado: **3-4 días**.
> **Tiene una decisión de producto pendiente** (§ A1).

## Alcance

| # | Hallazgo | Severidad |
|---|---|---|
| A1 | `consultar_libre` y `consultar_datos` se entregan a todos los usuarios sin filtrar por módulos | Alta |
| A2 | Conexión al ERP como superusuario; el validador deja pasar funciones administrativas | Alta |
| M4 | El validador de SQL y el compilador no tienen tests | Media |
| M7 | El error de una herramienta llega crudo al modelo | Media |

---

## Paso 0 — Medir antes de bloquear

Antes de restringir nada hay que saber qué se rompe. El auditor de
`free_query` ya guarda cada SQL ejecutado (`audit_query_model`).

1. Script `backend/scripts/audit_free_query.py` que lea la tabla de auditoría y reporte:
   - tablas y esquemas usados, ordenados por frecuencia;
   - funciones invocadas;
   - cuántas consultas quedarían fuera con cada opción de A1.
2. Correrlo sobre el historial disponible y **anexar el resultado a esta spec** antes de elegir.

**Criterio de aceptación:** la decisión de A1 se toma con esa tabla a la vista, no a ciegas.

---

## A1 — Permisos de datos por usuario

### Qué está mal

`build_savi_tools` (`registry.py:176-202`) entrega `consultar_libre` y
`consultar_datos` a cualquier usuario autenticado. `allowed_modules` solo se
usa para filtrar `consultar_conocimiento`. Un usuario con acceso solo a Ventas
puede preguntar por la nómina.

### Decisión pendiente: tres opciones

| Opción | Qué implica | Costo | Riesgo residual |
|---|---|---|---|
| **A. `consultar_libre` solo para administradores** | Un flag en `build_savi_tools`: si `allowed_modules is not None`, no se registra la tool. `consultar_datos` sigue para todos, acotado por el catálogo semántico. | Horas | Un usuario no admin pierde consultas libres. `consultar_datos` sigue sin filtrar por módulo. |
| **B. Lista de esquemas y tablas por módulo** | Un mapa `módulo → esquemas/tablas` en el catálogo; el validador AST rechaza cualquier tabla fuera del conjunto permitido del usuario. Aplica a `consultar_libre` y a `consultar_datos`. | 2-3 días | Hay que mantener el mapa cuando el ERP cambie; una tabla nueva no mapeada queda invisible (falla cerrado, que es lo correcto). |
| **C. Un rol de Postgres por perfil** | Cada perfil del ERP se corresponde con un rol con `GRANT SELECT` acotado; SAVI conecta con el rol del usuario. El motor aplica el permiso. | Semanas, y toca la instalación del cliente | El más sólido, pero exige coordinación con el ERP. |

**Recomendación:** **A ahora, B a continuación.** A cierra el agujero más
grande en horas; B es el modelo correcto a mediano plazo y se puede construir
con los datos del Paso 0. C queda como norte, atado a que el ERP exponga
perfiles.

### Cambios (opción A)

**`backend/app/modules/chat/infrastructure/llm/tools/registry.py`**:

```python
def build_savi_tools(*, conversation_id, allowed_modules, erp_database_id, document_context=None):
    """`allowed_modules=None` significa admin de la base: sin filtro."""
    is_admin = allowed_modules is None
    specs = [info_empresa, consultar_datos, consultar_conocimiento]
    if is_admin:
        # SQL libre solo para administradores de la base: la tool no distingue
        # esquemas ni módulos, así que en manos de un usuario común expone
        # nómina, contabilidad y todo lo demás sin importar sus permisos.
        specs.insert(2, consultar_libre_spec)
    return specs
```

El system prompt debe reflejarlo: sin la tool, el modelo no debe prometer
consultas libres. Revisar `system_prompt.py`.

### Criterios de aceptación

- [ ] Con `allowed_modules` distinto de `None`, `build_savi_tools` devuelve 3 tools y ninguna es `consultar_libre`.
- [ ] Con `allowed_modules=None`, devuelve 4.
- [ ] Un turno real con un usuario no admin (`FSCOGL17`) que pida datos de nómina responde que no puede, sin ejecutar SQL.
- [ ] El registro de auditoría no muestra consultas de ese usuario.

### Tests

| Test | Qué verifica |
|---|---|
| `test_tools_omit_free_query_for_non_admin` | La tool no se registra con módulos acotados. |
| `test_tools_include_free_query_for_admin` | Sí se registra sin filtro. |
| E2E de chat con `FSCOGL17` | Extiende el E2E existente de permisos: pregunta por un dato fuera de sus módulos y verifica la negativa. |

---

## A2 — Blindar el SQL y bajar privilegios del motor

Dos frentes independientes: uno en el código (validador) y otro en la
instalación (rol de Postgres). Los dos hacen falta; ninguno alcanza solo.

### A2.1 — Lista de funciones y catálogos permitidos

**Qué está mal.** `sql_validator.py` valida la *forma* (un SELECT, sin CTE, con
LIMIT) pero no *qué se invoca*. Verificado en ejecución: pasan y se ejecutan
`pg_read_file`, `pg_shadow`, `pg_cancel_backend`, `pg_sleep`, `set_config` y
`current_setting`.

**Cambios en `backend/app/modules/free_query/application/sql_validator.py`:**

1. Quitar `# pyright: basic` del encabezado: es una frontera de seguridad y va en strict.
2. Nueva regla `_reject_dangerous_functions(root)`:

```python
# Prefijos y nombres bloqueados. Lista de RECHAZO explícita, no de permiso:
# el catálogo de funciones de Postgres es enorme y una lista blanca cerrada
# rompería agregados y funciones de fecha legítimas. Se revisa con cada
# versión del motor.
_BLOCKED_PREFIXES = ("pg_", "lo_", "dblink", "postgres_fdw")
_BLOCKED_NAMES = {"set_config", "current_setting", "query_to_xml", "xpath"}
```

Recorrer `root.find_all(exp.Anonymous, exp.Func)` y rechazar por nombre.
Ojo: `sqlglot` modela muchas funciones estándar con clases propias, así que
el chequeo debe mirar el nombre emitido, no solo `exp.Anonymous`.

3. Nueva regla `_reject_system_catalogs(root)`: rechazar tablas cuyo esquema
   sea `pg_catalog` o `information_schema`, o cuyo nombre empiece con `pg_`.

   **Atención:** el mensaje de error actual de `execute_free_query.py:110-118`
   le pide explícitamente al modelo que consulte `information_schema.columns`
   para autocorregirse. Si se bloquea el catálogo, **hay que cambiar ese
   mensaje**, o el modelo entrará en un bucle de intentos fallidos. La
   alternativa es permitir `information_schema` y bloquear solo `pg_catalog`:
   decidir y dejarlo asentado acá.

4. Bajar `max_sql_length` no hace falta; sí revisar `max_estimated_rows`.

**Criterios de aceptación**

- [ ] Cada consulta de la tabla de A2 en `revision-general.md` es rechazada por el validador con un mensaje accionable.
- [ ] Un `SELECT` legítimo con `sum`, `count`, `date_trunc`, `coalesce` y `now()` sigue pasando.
- [ ] El archivo ya no tiene `# pyright: basic` y pasa strict.

### A2.2 — Rol de Postgres sin superusuario

**Qué está mal.** SAVI se conecta al ERP como `postgres` (verificado:
`is_superuser = on`). Con eso, cualquier falla del validador escala a lectura
de archivos del servidor.

**Cambios:**

1. `backend/docs/erp_clients/` (o donde viva la guía de alta de clientes): SQL de referencia.

   ```sql
   CREATE ROLE savi_lectura LOGIN PASSWORD '...';
   GRANT CONNECT ON DATABASE <base> TO savi_lectura;
   GRANT USAGE ON SCHEMA <cada esquema del ERP> TO savi_lectura;
   GRANT SELECT ON ALL TABLES IN SCHEMA <cada esquema> TO savi_lectura;
   ALTER DEFAULT PRIVILEGES IN SCHEMA <cada esquema> GRANT SELECT ON TABLES TO savi_lectura;
   ```

2. **Detección y aviso**: al probar la conexión (`postgres_connection_tester.py`)
   consultar `current_setting('is_superuser')` y devolverlo en el resultado.
   La pantalla de bases muestra una advertencia visible cuando el usuario
   configurado es superusuario, con enlace a la guía.

3. No bloquear el alta: hay instalaciones existentes y romperlas sería peor.

**Criterios de aceptación**

- [ ] `test-connection` devuelve `is_superuser` y la interfaz lo muestra como advertencia.
- [ ] La guía de alta trae el SQL probado contra el ERP de desarrollo.
- [ ] Con `savi_lectura`, el login, `consultar_datos` y `consultar_libre` siguen funcionando (prueba manual contra `farmacias_similares`).

---

## M4 — Tests de las fronteras de seguridad

`free_query` y `data_query` no tienen **ningún** test. Son justo los módulos
que deciden qué SQL toca el ERP.

### Cobertura mínima

**`backend/tests/unit/modules/free_query/test_sql_validator.py`**

| Caso | Esperado |
|---|---|
| `SELECT` simple sin LIMIT | Pasa, con LIMIT agregado al cap |
| `LIMIT 999999` | Se baja al cap |
| `INSERT` / `UPDATE` / `DELETE` / `DROP` | Rechazado |
| Dos sentencias separadas por `;` | Rechazado |
| `WITH`, `UNION`, `LATERAL`, `OFFSET` | Rechazado, uno por caso |
| `SELECT *` en el root; `SELECT 1` en subquery | Rechazado / permitido |
| Subqueries de profundidad 3 | Rechazado |
| `pg_read_file`, `pg_sleep`, `set_config`, `dblink`, `pg_terminate_backend` | Rechazado (A2.1) |
| `pg_catalog.pg_shadow`, `information_schema.columns` | Según lo decidido en A2.1 |
| Agregados y funciones de fecha legítimas | Permitido |
| Comentarios `--` y `/* */` con SQL adentro | Se descartan al re-emitir desde el AST |

**`backend/tests/unit/modules/data_query/test_query_compiler.py`**

| Caso | Esperado |
|---|---|
| Dimensión o métrica inexistente | `InvalidQueryError` |
| Valores con comillas, `%`, `;` | Van como bind params, no alteran el SQL |
| `orden.campo` fuera de los alias seleccionados | Se ignora |
| `limite` por encima del máximo de la entidad | Se recorta |
| Modo `registro` sin filtro de clave | Rechazado |

**Criterio de aceptación:** ambos archivos existen, cubren la tabla completa y
la suite queda en verde.

---

## M7 — El error de una herramienta no viaja crudo al modelo

**Qué está mal.** `registry.py:150` devuelve `f"La herramienta falló: {e}"`.
Ese texto puede traer host, ruta o SQL, y el modelo lo repite al usuario.

**Cambios:**

```python
except Exception as e:  # noqa: BLE001
    log.exception("tool_failed name=%s", name)
    return ToolResult(
        text="La herramienta falló. Probá reformular la consulta.",
        is_error=True,
    )
```

Las excepciones **tipadas** del dominio (`AstValidationError`,
`ExplainGateError`, `DatabaseExecutionError`) sí deben seguir llegando al
modelo: su mensaje es accionable y está saneado a propósito. Distinguir por
tipo, no tapar todo.

**Criterios de aceptación**

- [ ] Una excepción inesperada produce un mensaje genérico y una entrada completa en el log.
- [ ] Los errores tipados de `free_query` siguen llegando con su texto.

**Test:** `test_tool_generic_error_is_sanitized`.

---

## Resultado de la fase

- Un usuario común ya no puede consultar datos fuera de sus módulos (opción A) o fuera de sus tablas permitidas (opción B).
- Aunque el validador fallara, el motor ya no corre como superusuario en las instalaciones nuevas, y las viejas tienen advertencia visible.
- Las dos fronteras quedan con tests de regresión.
