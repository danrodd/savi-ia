"""Validador del SQL que escribe el modelo.

Es una frontera de seguridad y no tenía ningún test. Los casos "peligrosos" no
son hipotéticos: se ejecutaron de verdad contra el ERP de desarrollo antes de
la Fase 1 (ver `docs/revision-general.md`, hallazgo A2).
"""

from __future__ import annotations

import pytest

from app.modules.free_query.application.sql_validator import validate_and_normalize
from app.modules.free_query.domain.errors import AstValidationError
from app.modules.free_query.domain.policy import DEFAULT_POLICY, FreeQueryPolicy


def _valida(sql: str, policy: FreeQueryPolicy = DEFAULT_POLICY) -> str:
    return validate_and_normalize(sql, policy)


# ── Forma ────────────────────────────────────────────────────────────────


def test_adds_the_limit_when_missing() -> None:
    assert "LIMIT 50" in _valida("SELECT nombre FROM terceros")


def test_caps_a_limit_over_the_policy() -> None:
    resultado = _valida("SELECT nombre FROM terceros LIMIT 999999")

    assert "LIMIT 50" in resultado
    assert "999999" not in resultado


def test_keeps_a_smaller_limit() -> None:
    assert "LIMIT 10" in _valida("SELECT nombre FROM terceros LIMIT 10")


def test_rejects_a_zero_or_negative_limit() -> None:
    """`LIMIT 0` no trae filas y `LIMIT -1` es un error: se normaliza al cap."""
    assert "LIMIT 50" in _valida("SELECT nombre FROM terceros LIMIT 0")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO terceros (nombre) VALUES ('x')",
        "UPDATE terceros SET nombre = 'x'",
        "DELETE FROM terceros",
        "DROP TABLE terceros",
        "TRUNCATE terceros",
        "CREATE TABLE t (a int)",
        "GRANT ALL ON terceros TO public",
    ],
)
def test_rejects_anything_that_is_not_a_select(sql: str) -> None:
    with pytest.raises(AstValidationError):
        _valida(sql)


def test_rejects_multiple_statements() -> None:
    with pytest.raises(AstValidationError, match="UNA sentencia"):
        _valida("SELECT nombre FROM terceros; DROP TABLE terceros")


@pytest.mark.parametrize(
    ("sql", "motivo"),
    [
        ("WITH t AS (SELECT 1 AS a) SELECT a FROM t", "WITH"),
        ("SELECT a FROM x UNION SELECT b FROM y", "UNION"),
        ("SELECT a FROM x INTERSECT SELECT b FROM y", "INTERSECT"),
        ("SELECT a FROM x EXCEPT SELECT b FROM y", "EXCEPT"),
        ("SELECT nombre FROM terceros OFFSET 10", "OFFSET"),
    ],
)
def test_rejects_constructs_that_evade_the_row_cap(sql: str, motivo: str) -> None:
    with pytest.raises(AstValidationError, match=motivo):
        _valida(sql)


def test_rejects_select_star_at_the_root() -> None:
    with pytest.raises(AstValidationError, match=r"SELECT \*"):
        _valida("SELECT * FROM terceros")


def test_allows_select_one_inside_a_subquery() -> None:
    """`EXISTS (SELECT 1 …)` es legítimo: el LIMIT del outer manda."""
    sql = "SELECT nombre FROM terceros t WHERE EXISTS (SELECT 1 FROM ventas v WHERE v.id = t.id)"

    assert _valida(sql)


def test_rejects_too_much_nesting() -> None:
    sql = "SELECT a FROM (SELECT a FROM (SELECT a FROM (SELECT a FROM t) x) y) z"

    with pytest.raises(AstValidationError, match="subqueries"):
        _valida(sql)


def test_rejects_sql_that_does_not_parse() -> None:
    with pytest.raises(AstValidationError, match="parsear"):
        _valida("SELECT FROM WHERE ((((")


def test_rejects_an_empty_query() -> None:
    with pytest.raises(AstValidationError, match="vacío"):
        _valida("   ")


def test_rejects_an_overly_long_query() -> None:
    with pytest.raises(AstValidationError, match="demasiado largo"):
        _valida("SELECT nombre FROM terceros WHERE nombre = '" + "x" * 5000 + "'")


def test_comments_are_dropped_by_reemitting_from_the_ast() -> None:
    """El SQL se re-emite desde el AST: lo que venga escondido en un
    comentario no llega al motor."""
    resultado = _valida("SELECT nombre /* ; DROP TABLE terceros */ FROM terceros")

    assert "DROP" not in resultado.upper()


# ── Contenido: funciones y catálogos (Fase 1) ────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_read_file('postgresql.conf', 0, 60) AS f",
        "SELECT pg_ls_dir('/') AS d",
        "SELECT pg_sleep(55) AS s",
        "SELECT pg_terminate_backend(123) AS k",
        "SELECT pg_cancel_backend(123) AS k",
        "SELECT set_config('statement_timeout', '0', false) AS x",
        "SELECT current_setting('is_superuser') AS s",
        "SELECT lo_import('/etc/passwd') AS oid",
        "SELECT v FROM dblink('dbname=x', 'SELECT 1') AS t(v text)",
        "SELECT dblink_exec('dbname=x', 'DELETE FROM ventas') AS r",
    ],
)
def test_rejects_engine_administration_functions(sql: str) -> None:
    """Todas estas se EJECUTABAN antes de la Fase 1. El modo solo lectura no
    las frena: ninguna escribe datos."""
    with pytest.raises(AstValidationError, match="no está permitida"):
        _valida(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) AS n FROM pg_shadow",
        "SELECT usename FROM pg_catalog.pg_user",
        "SELECT pid FROM pg_stat_activity",
    ],
)
def test_rejects_system_catalogs(sql: str) -> None:
    with pytest.raises(AstValidationError, match="catálogo interno"):
        _valida(sql)


def test_allows_information_schema() -> None:
    """A propósito: el mensaje de error le pide al modelo que la consulte
    para descubrir nombres y autocorregirse. Solo expone nombres de objetos,
    respetando los permisos del rol."""
    sql = "SELECT column_name FROM information_schema.columns WHERE table_name = 'ventas'"

    assert _valida(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT sum(total) AS t FROM ventas",
        "SELECT count(*) AS n, avg(total) AS p FROM ventas",
        "SELECT date_trunc('month', fecha) AS m FROM ventas GROUP BY 1",
        "SELECT coalesce(nombre, '-') AS n FROM terceros",
        "SELECT upper(codigo) AS c, lower(nombre) AS n FROM terceros",
        "SELECT nombre FROM terceros WHERE fecha > now() - interval '30 days'",
        "SELECT extract(year FROM fecha) AS anio FROM ventas",
        "SELECT round(total, 2) AS t FROM ventas",
    ],
)
def test_allows_ordinary_query_functions(sql: str) -> None:
    """La lista de rechazo no puede llevarse puesto el uso legítimo."""
    assert _valida(sql)
