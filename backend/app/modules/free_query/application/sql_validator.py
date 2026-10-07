"""Validador estructural del SQL del LLM con sqlglot.

Política de FORMA:
- Una sola sentencia.
- Solo SELECT (con FROM, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT).
- Sin OFFSET (impide paginación multi-turno).
- Sin CTE (WITH ...): el LIMIT global se evade fácilmente con CTE.
- Sin UNION/INTERSECT/EXCEPT: cada rama duplica el cap efectivo.
- Sin LATERAL: multiplica filas por cada fila de la outer query.
- Sin SELECT * salvo en subqueries específicas (ej. EXISTS).
- Sin subqueries de profundidad > política.
- LIMIT obligatorio y ≤ política. Si falta, lo agregamos; si es mayor,
  lo bajamos al cap. Devolvemos el SQL final (puede diferir del input).

Política de CONTENIDO (agregada en la Fase 1 de seguridad):
- Sin funciones de administración del motor ni de acceso al sistema de
  archivos.
- Sin catálogos del sistema.

Por qué hace falta lo segundo: la forma sola no alcanza. Verificado contra el
ERP de desarrollo, estas consultas pasaban la validación anterior y se
ejecutaban, porque un `SELECT` que llama funciones no deja de ser un `SELECT`:

    SELECT pg_read_file('postgresql.conf', 0, 60)      → lee archivos del servidor
    SELECT count(*) FROM pg_shadow WHERE passwd IS NOT NULL  → hashes de contraseñas
    SELECT pg_cancel_backend(pid) FROM pg_stat_activity      → corta conexiones del ERP
    SELECT pg_sleep(55)                                      → retiene la conexión

El modo solo lectura del motor **no** las frena: ninguna escribe datos. Y la
conexión suele ser superusuario (ver `docs/seguridad/02-fase-1-datos-erp.md`),
con lo que el alcance es la máquina entera, no solo la base.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import sqlglot
from sqlglot import errors as sqlglot_errors
from sqlglot import exp

from app.modules.free_query.domain.errors import AstValidationError
from app.modules.free_query.domain.policy import FreeQueryPolicy

_DIALECT = "postgres"

# Lista de RECHAZO y no de permiso: el catálogo de funciones de Postgres es
# enorme y una lista blanca cerrada rompería agregados, fechas y texto, que es
# el 99% del uso legítimo. Se revisa al subir de versión del motor.
BLOCKED_FUNCTION_PREFIXES: frozenset[str] = frozenset(
    {
        "pg_",  # pg_read_file, pg_sleep, pg_terminate_backend, pg_ls_dir…
        "lo_",  # objetos grandes: lo_import / lo_export tocan el disco
        "dblink",  # abre una conexión NUEVA, que no hereda el modo solo lectura
        "postgres_fdw",
        "dbms_",  # por si alguna base trae compatibilidad Oracle
    }
)

BLOCKED_FUNCTION_NAMES: frozenset[str] = frozenset(
    {
        # Cambian la sesión: `statement_timeout`, `default_transaction_read_only`…
        "set_config",
        "current_setting",
        # Lecturas de metadatos por vías indirectas.
        "query_to_xml",
        "query_to_xmlschema",
        "xpath",
        "to_regclass",
        "to_regproc",
    }
)

# `information_schema` NO se bloquea a propósito: el mensaje de error de
# `execute_free_query` le pide explícitamente al modelo que la consulte para
# descubrir nombres de columnas y autocorregirse. Bloquearla lo dejaría en un
# bucle de intentos fallidos. Solo expone nombres de objetos, no datos ni
# credenciales, y respeta los permisos del rol.
BLOCKED_SCHEMAS: frozenset[str] = frozenset({"pg_catalog", "pg_toast"})

# Tablas del sistema accesibles sin calificar el esquema: `SELECT * FROM
# pg_shadow` funciona sin escribir `pg_catalog.`.
_BLOCKED_TABLE_PREFIX = "pg_"

# Datos personales de terceros que nunca se devuelven al usuario
# (`docs/DB_MAP.md`). El catálogo semántico ya no los expone, pero el SQL libre
# sí podía: medido, un "¿qué proveedores están bloqueados?" mostró el número de
# identificación del tercero. Se bloquean en lo que la consulta DEVUELVE; en un
# WHERE siguen sirviendo para buscar (encontrar por NIT no lo muestra), y dentro
# de un agregado (`COUNT(email)`) no exponen el valor.
SENSITIVE_COLUMNS: frozenset[str] = frozenset(
    {
        "numeroidentificacion",
        "telefonofijo",
        "telefono",
        "celular",
        "email",
        "correo",
        "correoelectronico",
        "direccion",
    }
)


def validate_and_normalize(sql: str, policy: FreeQueryPolicy) -> str:
    """Valida el SQL contra la política y devuelve el SQL final a ejecutar.

    Levanta `AstValidationError` con mensaje accionable si algo no
    cumple. El SQL devuelto tiene `LIMIT` saneado y queda re-emitido
    desde el AST (formato canónico).
    """
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise AstValidationError("El SQL está vacío.")
    if len(sql) > policy.max_sql_length:
        raise AstValidationError(
            f"El SQL es demasiado largo ({len(sql)} chars; máximo "
            f"{policy.max_sql_length}). Reformulalo más conciso."
        )

    try:
        statements = sqlglot.parse(sql, dialect=_DIALECT)
    except sqlglot_errors.ParseError as e:
        raise AstValidationError(
            f"SQL inválido: no se pudo parsear ({e}). Revisá la sintaxis."
        ) from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise AstValidationError("Solo se permite UNA sentencia SQL por consulta.")

    root = statements[0]
    if isinstance(root, exp.Union | exp.Intersect | exp.Except):
        # Antes caían en el mensaje genérico de abajo, que no le decía al
        # modelo qué había hecho mal: con un `UNION` en la raíz el nodo no es
        # `Select`, así que `_reject_unions_anywhere` nunca llegaba a correr.
        kind = type(root).__name__.upper()
        raise AstValidationError(f"{kind} no está permitido. Hacé una sola consulta por turno.")
    if not isinstance(root, exp.Select):
        raise AstValidationError(
            "Solo se permite SELECT. Operaciones de escritura, EXEC y DDL están bloqueadas."
        )

    _reject_unions_anywhere(root)
    _reject_with_ctes(root)
    _reject_lateral_joins(root)
    _reject_offset(root)
    _reject_select_star_top_level(root)
    _reject_dangerous_functions(root)
    _reject_system_catalogs(root)
    _reject_sensitive_columns(root)
    _check_subquery_depth(root, policy)
    _make_date_ranges_inclusive(root)

    # Saneamos el LIMIT del root: si falta o es mayor que el cap, lo
    # ponemos en el cap.
    _enforce_limit(root, policy)

    # Re-emitimos el SQL desde el AST: formato canónico, identifiers quoted
    # consistentes y sin caracteres invisibles colados.
    #
    # `comments=False` explícito: por defecto sqlglot los CONSERVA. Un
    # comentario SQL no se ejecuta, así que no era explotable, pero el
    # comentario de este código decía que se descartaban y no era cierto —
    # y no hay motivo para reenviarle al ERP texto libre escrito por el
    # modelo.
    return root.sql(dialect=_DIALECT, pretty=False, comments=False)


# ── reglas ─────────────────────────────────────────────────────────────


def _reject_unions_anywhere(root: exp.Select) -> None:
    # `find_all` recorre todo el AST incluyendo subqueries.
    for node in root.find_all(exp.Union, exp.Intersect, exp.Except):
        kind = type(node).__name__.upper()
        raise AstValidationError(f"{kind} no está permitido. Hacé una sola consulta por turno.")


def _reject_with_ctes(root: exp.Select) -> None:
    if root.args.get("with") is not None or any(root.find_all(exp.With)):
        raise AstValidationError(
            "WITH (CTEs) no está permitido. Expresá la lógica en una sola "
            "consulta con joins y subqueries simples."
        )


def _reject_lateral_joins(root: exp.Select) -> None:
    for _ in root.find_all(exp.Lateral):
        raise AstValidationError("LATERAL no está permitido. Reemplazalo por un join normal.")


def _reject_offset(root: exp.Select) -> None:
    for _ in root.find_all(exp.Offset):
        raise AstValidationError(
            "OFFSET no está permitido (impide paginación). Si necesitás "
            "ver otro subconjunto, afiná los filtros (fecha, cliente, "
            "producto, etc.) en lugar de paginar."
        )


def _reject_select_star_top_level(root: exp.Select) -> None:
    # En el SELECT raíz no permitimos `*` o `tabla.*`: el LLM debe
    # enumerar las columnas que necesita. En subqueries lo dejamos pasar
    # (ej. `EXISTS(SELECT 1 FROM ...)` no es problema y el LIMIT del
    # outer manda).
    for projection in root.expressions:
        if isinstance(projection, exp.Star):
            raise AstValidationError(
                "SELECT * no está permitido. Listá explícitamente las columnas que necesitás."
            )
        if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
            raise AstValidationError(
                "tabla.* no está permitido. Listá explícitamente las columnas que necesitás."
            )


def _function_name(node: exp.Func) -> str:
    """Nombre invocable del nodo, en minúsculas.

    `sqlglot` modela las funciones conocidas con clases propias (`exp.Sum`,
    `exp.DateTrunc`…) y las desconocidas como `exp.Anonymous`. Mirar solo
    `exp.Anonymous` dejaría pasar cualquier función que sqlglot reconozca, así
    que se pregunta por el nombre con el que se emite."""
    if isinstance(node, exp.Anonymous):
        return str(node.name or "").lower()
    nombre: object = node.sql_name()  # pyright: ignore[reportUnknownMemberType]
    return str(nombre).lower()


def _reject_dangerous_functions(root: exp.Select) -> None:
    for node in root.find_all(exp.Func):
        nombre = _function_name(node)
        if not nombre:
            continue
        if nombre in BLOCKED_FUNCTION_NAMES or nombre.startswith(tuple(BLOCKED_FUNCTION_PREFIXES)):
            raise AstValidationError(
                f"La función '{nombre}' no está permitida: solo se pueden usar "
                "funciones de consulta sobre los datos (agregados, fechas, texto), "
                "no de administración del motor."
            )


def _reject_system_catalogs(root: exp.Select) -> None:
    for node in root.find_all(exp.Table):
        esquema = (node.db or "").lower()
        tabla = (node.name or "").lower()
        if esquema in BLOCKED_SCHEMAS or tabla.startswith(_BLOCKED_TABLE_PREFIX):
            objetivo = f"{esquema}.{tabla}".lstrip(".")
            raise AstValidationError(
                f"La tabla '{objetivo}' es del catálogo interno de Postgres y no "
                "se puede consultar. Para descubrir nombres de tablas o columnas "
                "usá `information_schema`."
            )


def _reject_sensitive_columns(root: exp.Select) -> None:
    # Cada SELECT, también los de subqueries: si no, `SELECT x FROM (SELECT
    # email AS x ...)` lo devolvería renombrado.
    for select in [root, *root.find_all(exp.Select)]:
        for projection in select.expressions:
            for column in projection.find_all(exp.Column):
                if column.name.lower() not in SENSITIVE_COLUMNS:
                    continue
                if column.find_ancestor(exp.AggFunc) is not None:
                    continue
                raise AstValidationError(
                    f"La columna '{column.name}' es un dato personal y no se puede "
                    "devolver (identificación, teléfono, email, dirección). Mostrá "
                    "el nombre y el código del tercero en su lugar."
                )


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _make_date_ranges_inclusive(root: exp.Select) -> None:
    """`fecha BETWEEN '2026-01-01' AND '2026-03-31'` deja afuera el 31 entero
    cuando `fecha` tiene hora: compara contra la medianoche. Medido con Gemini:
    marzo dio $2.678 M en vez de $2.712 M (1.532 facturas del día 31 menos).

    Se reescribe a `>= inicio AND < día siguiente al fin`, que es lo mismo para
    una columna DATE y lo correcto para una con hora. El catálogo semántico ya
    lo hacía así (`query_compiler`); esto lo extiende al SQL libre sin depender
    de que el modelo lo sepa."""
    for between in list(root.find_all(exp.Between)):
        low, high = between.args.get("low"), between.args.get("high")
        if not (isinstance(low, exp.Literal) and isinstance(high, exp.Literal)):
            continue
        if not (low.is_string and high.is_string):
            continue
        if not (_DATE_ONLY.match(low.this) and _DATE_ONLY.match(high.this)):
            continue
        try:
            next_day = date.fromisoformat(high.this) + timedelta(days=1)
        except ValueError:
            continue
        column = between.this
        between.replace(
            exp.paren(
                exp.and_(
                    exp.GTE(this=column.copy(), expression=exp.Literal.string(low.this)),
                    exp.LT(this=column.copy(), expression=exp.Literal.string(next_day.isoformat())),
                )
            )
        )


def _check_subquery_depth(root: exp.Select, policy: FreeQueryPolicy) -> None:
    # Contamos la profundidad máxima de Subquery / Select anidadas debajo
    # del root, ignorándolo a él mismo.
    max_depth = _depth(root) - 1
    if max_depth > policy.max_subquery_depth:
        raise AstValidationError(
            f"Demasiados niveles de subqueries ({max_depth}; máximo "
            f"{policy.max_subquery_depth}). Aplaná la consulta."
        )


def _depth(node: exp.Expression) -> int:  # pyright: ignore[reportPrivateImportUsage]
    deepest = 0
    for child in node.walk(prune=lambda n: False):
        # walk() devuelve tuplas (node, parent, key) en algunas versiones;
        # en versiones recientes devuelve sólo el node. Adaptamos.
        n = child[0] if isinstance(child, tuple) else child
        if isinstance(n, (exp.Select, exp.Subquery)) and n is not node:
            d = 1 + _depth(n)
            if d > deepest:
                deepest = d
    return deepest


def _enforce_limit(root: exp.Select, policy: FreeQueryPolicy) -> None:
    existing = root.args.get("limit")
    if existing is None:
        root.set(
            "limit",
            exp.Limit(expression=exp.Literal.number(policy.max_rows)),
        )
        return
    # Si el LIMIT actual es un literal numérico, lo bajamos si pasa el cap.
    inner = existing.expression
    if isinstance(inner, exp.Literal) and inner.is_int:
        n = int(inner.this)
        if n > policy.max_rows or n <= 0:
            existing.set("expression", exp.Literal.number(policy.max_rows))
        return
    # LIMIT con expresión no literal (ej. parámetro o función): reemplazo.
    existing.set("expression", exp.Literal.number(policy.max_rows))
