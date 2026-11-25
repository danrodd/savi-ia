"""Tablas del ERP que lee una consulta libre.

Sirve para saber qué le falta al catálogo de datos: si muchas preguntas caen en
SQL libre sobre `Contabilidad.MovimientoContable`, esa tabla merece una entidad.
Son nombres del esquema del ERP, iguales en todos los clientes: no llevan datos
de la consulta (ni valores, ni filtros, ni columnas).
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import errors as sqlglot_errors
from sqlglot import exp

_DIALECT = "postgres"
# Lo que sale de acá puede viajar a Cloud: solo identificadores simples.
_NAME = re.compile(r"^[A-Za-z0-9_]{1,63}$")
# Tablas distintas por consulta que se informan; una consulta con más es rara.
MAX_TABLES = 20
_SYSTEM_SCHEMAS = frozenset({"information_schema", "pg_catalog"})


def referenced_tables(sql: str) -> list[str]:
    """`Esquema.Tabla` de cada tabla que lee `sql`, ordenadas y sin repetir.

    Deja afuera los CTE (`WITH x AS …` no es una tabla del ERP), los catálogos
    del sistema y lo que no tiene esquema. Si la consulta no se puede leer,
    devuelve una lista vacía: esto informa, no valida.
    """
    try:
        statements = sqlglot.parse(sql, dialect=_DIALECT)
    except sqlglot_errors.ParseError:
        return []
    found: set[str] = set()
    for statement in statements:
        if statement is None:
            continue
        ctes = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
        for table in statement.find_all(exp.Table):
            schema, name = table.db, table.name
            if not schema or not name:
                continue
            if schema.lower() in _SYSTEM_SCHEMAS or name.lower() in ctes:
                continue
            if _NAME.match(schema) and _NAME.match(name):
                found.add(f"{schema}.{name}")
    return sorted(found)[:MAX_TABLES]
