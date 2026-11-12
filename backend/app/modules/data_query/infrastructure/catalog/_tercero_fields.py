"""Datos del tercero por nivel de permiso, compartidos entre entidades.

Ver `docs/plataforma/10-datos-por-permiso.md`:

- **Personal** (identificación, teléfonos, correo, dirección...): administrador o
  módulo TERCERO.
- **Bancario** (cuentas de `Tercero.TerceroBanco`): administrador o módulo
  CUENTAPAGAR.
- **Negocio** (municipio, cupo, vendedor, último movimiento): quien ve la entidad.

Lo personal y lo bancario de un tercero que aparece en `Seguridad.TerceroVip`
sale vacío para quien no es administrador. Hoy esa tabla está vacía en todos
los clientes conocidos; es la regla conservadora hasta confirmar con el equipo
del ERP qué significa (§5.8 de la spec).

El ERP guarda vacío como `''`: todo pasa por `NULLIF(TRIM(...), '')`.
"""

from __future__ import annotations

from app.modules.data_query.domain.semantic_model import (
    VIEWER_PLACEHOLDER,
    DimensionDef,
    FieldDef,
    FilterDef,
)
from app.modules.data_query.domain.semantic_query import FilterOp
from app.modules.data_query.infrastructure.catalog._names import tercero_display_name

PERSONAL_MODULES = ("TERCERO",)
BANK_MODULES = ("CUENTAPAGAR",)


def _text(column: str, alias: str) -> str:
    return f"NULLIF(TRIM({alias}.\"{column}\"), '')"


def _vip_guard(sql: str, alias: str) -> str:
    """Vacío para quien no está listado en `TerceroVip` para ese tercero.

    `VIEWER_PLACEHOLDER` lo reemplaza `scoped_for` por el `idUsuario` de quien
    pregunta en esa base, como entero; sin usuario conocido queda `NULL` y el
    dato sale vacío.
    """
    return (
        f'CASE WHEN EXISTS (SELECT 1 FROM "Seguridad"."TerceroVip" vip '
        f'WHERE vip."idTercero" = {alias}."idTercero") '
        f'AND NOT EXISTS (SELECT 1 FROM "Seguridad"."TerceroVip" vip '
        f'WHERE vip."idTercero" = {alias}."idTercero" AND vip."idUsuario" = {VIEWER_PLACEHOLDER}) '
        f"THEN NULL ELSE {sql} END"
    )


def _personal(name: str, sql: str, label: str, alias: str, requires: tuple[str, ...]) -> FieldDef:
    return FieldDef(
        name,
        sql,
        label,
        requires=requires,
        required_modules=PERSONAL_MODULES,
        restricted_sql=_vip_guard(sql, alias),
        default=False,
    )


def contact_fields(alias: str = "t", requires: tuple[str, ...] = ()) -> dict[str, FieldDef]:
    """Identificación y contacto del tercero (nivel personal)."""
    identification = (
        f'{_text("numeroIdentificacion", alias)} || CASE WHEN {alias}."digitoVerificacion" > 0 '
        f"THEN '-' || {alias}.\"digitoVerificacion\" ELSE '' END"
    )
    fields = [
        ("identificacion", identification, "NIT o cédula"),
        ("telefono", _text("telefonoFijo", alias), "Teléfono"),
        ("celular", _text("celular", alias), "Celular"),
        ("email", _text("email", alias), "Correo"),
        ("direccion", _text("direccion", alias), "Dirección"),
    ]
    return {name: _personal(name, sql, label, alias, requires) for name, sql, label in fields}


def contact_dimensions(alias: str = "t", requires: tuple[str, ...] = ()) -> dict[str, DimensionDef]:
    """Los mismos datos de contacto para agrupar: "clientes que compraron X,
    con su celular" es un agregado por cliente, no un detalle."""
    return {
        name: DimensionDef(
            name,
            f.sql,
            f.label,
            requires=requires,
            required_modules=f.required_modules,
            restricted_sql=f.restricted_sql,
        )
        for name, f in contact_fields(alias, requires).items()
    }


def municipality_sql(alias: str = "t") -> str:
    return (
        f'(SELECT m."descripcion" FROM "General"."Municipio" m '
        f'WHERE m."idMunicipio" = {alias}."idMunicipio")'
    )


def salesperson_sql(alias: str = "t") -> str:
    return (
        f'(SELECT {tercero_display_name("e")} FROM "Tercero"."Tercero" e '
        f'WHERE e."idTercero" = {alias}."idTerceroEmpleado")'
    )


def group_sql(alias: str = "t") -> str:
    return (
        f'(SELECT g."descripcion" FROM "Tercero"."GrupoTercero" g '
        f'WHERE g."idGrupoTercero" = {alias}."idGrupoTercero")'
    )


def tercero_detail_fields(alias: str = "t") -> dict[str, FieldDef]:
    """Lo que suma la entidad `terceros`: negocio, personal y bancario."""
    business = {
        "municipio": FieldDef("municipio", municipality_sql(alias), "Municipio", default=False),
        "vendedor": FieldDef("vendedor", salesperson_sql(alias), "Vendedor", default=False),
        "grupo": FieldDef("grupo", group_sql(alias), "Grupo", default=False),
        "cupo_credito": FieldDef(
            "cupo_credito", f'{alias}."cupoCredito"', "Cupo de crédito", default=False
        ),
        "dias_credito": FieldDef(
            "dias_credito", f'{alias}."diasCredito"', "Días de crédito", default=False
        ),
        "sin_credito": FieldDef(
            "sin_credito", f'{alias}."sinCredito"', "Sin crédito", default=False
        ),
        "ultimo_movimiento": FieldDef(
            "ultimo_movimiento",
            f'{alias}."fechaUltimoMovimiento"::date',
            "Último movimiento",
            default=False,
        ),
    }
    personal = {
        **contact_fields(alias),
        "representante_legal": _personal(
            "representante_legal",
            _text("representanteLegal", alias),
            "Representante legal",
            alias,
            (),
        ),
        "fecha_nacimiento": _personal(
            "fecha_nacimiento",
            f'{alias}."fechaNacimiento"::date',
            "Fecha de nacimiento",
            alias,
            (),
        ),
    }
    accounts = (
        f"(SELECT string_agg(COALESCE(NULLIF(TRIM(b.\"nombre\"), ''), 'Banco') || ' ' || "
        f'tb."numeroCuenta", \'; \') FROM "Tercero"."TerceroBanco" tb '
        f'LEFT JOIN "Tercero"."Banco" b ON b."idBanco" = tb."idBanco" '
        f'WHERE tb."idTercero" = {alias}."idTercero")'
    )
    bank = {
        "cuentas_bancarias": FieldDef(
            "cuentas_bancarias",
            accounts,
            "Cuentas bancarias",
            required_modules=BANK_MODULES,
            restricted_sql=_vip_guard(accounts, alias),
            default=False,
        )
    }
    return {**business, **personal, **bank}


def tercero_detail_dimensions(alias: str = "t") -> dict[str, DimensionDef]:
    return {
        "municipio": DimensionDef("municipio", municipality_sql(alias), "Municipio"),
        "vendedor": DimensionDef("vendedor", salesperson_sql(alias), "Vendedor"),
        "grupo": DimensionDef("grupo", group_sql(alias), "Grupo"),
    }


def tercero_detail_filters(alias: str = "t") -> dict[str, FilterDef]:
    return {
        "municipio": FilterDef("municipio", municipality_sql(alias), (FilterOp.CONTAINS,)),
        "vendedor": FilterDef("vendedor", salesperson_sql(alias), (FilterOp.CONTAINS,)),
        "ultimo_movimiento": FilterDef(
            "ultimo_movimiento",
            f'{alias}."fechaUltimoMovimiento"',
            (FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE, FilterOp.BETWEEN),
            value_type="date",
        ),
        # Buscar por NIT no lo muestra: se puede filtrar sin permiso de contacto.
        "identificacion": FilterDef(
            "identificacion", f'TRIM({alias}."numeroIdentificacion")', (FilterOp.EQ,)
        ),
    }
