# pyright: basic
"""Validador estructural del SQL del LLM con sqlglot.

Política:
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
"""
from __future__ import annotations

import sqlglot
from sqlglot import errors as sqlglot_errors
from sqlglot import exp

from app.modules.free_query.domain.errors import AstValidationError
from app.modules.free_query.domain.policy import FreeQueryPolicy

_DIALECT = "postgres"


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
        raise AstValidationError(
            "Solo se permite UNA sentencia SQL por consulta."
        )

    root = statements[0]
    if not isinstance(root, exp.Select):
        raise AstValidationError(
            "Solo se permite SELECT. Operaciones de escritura, EXEC y DDL "
            "están bloqueadas."
        )

    _reject_unions_anywhere(root)
    _reject_with_ctes(root)
    _reject_lateral_joins(root)
    _reject_offset(root)
    _reject_select_star_top_level(root)
    _check_subquery_depth(root, policy)

    # Saneamos el LIMIT del root: si falta o es mayor que el cap, lo
    # ponemos en el cap.
    _enforce_limit(root, policy)

    # Re-emitimos el SQL desde el AST: formato canónico, identifiers
    # quoted consistentes, y se descartan posibles comentarios o
    # caracteres invisibles colados.
    return root.sql(dialect=_DIALECT, pretty=False)


# ── reglas ─────────────────────────────────────────────────────────────


def _reject_unions_anywhere(root: exp.Select) -> None:
    # `find_all` recorre todo el AST incluyendo subqueries.
    for node in root.find_all(exp.Union, exp.Intersect, exp.Except):
        kind = type(node).__name__.upper()
        raise AstValidationError(
            f"{kind} no está permitido. Hacé una sola consulta por turno."
        )


def _reject_with_ctes(root: exp.Select) -> None:
    if root.args.get("with") is not None or any(root.find_all(exp.With)):
        raise AstValidationError(
            "WITH (CTEs) no está permitido. Expresá la lógica en una sola "
            "consulta con joins y subqueries simples."
        )


def _reject_lateral_joins(root: exp.Select) -> None:
    for _ in root.find_all(exp.Lateral):
        raise AstValidationError(
            "LATERAL no está permitido. Reemplazalo por un join normal."
        )


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
                "SELECT * no está permitido. Listá explícitamente las "
                "columnas que necesitás."
            )
        if isinstance(projection, exp.Column) and isinstance(
            projection.this, exp.Star
        ):
            raise AstValidationError(
                "tabla.* no está permitido. Listá explícitamente las "
                "columnas que necesitás."
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
