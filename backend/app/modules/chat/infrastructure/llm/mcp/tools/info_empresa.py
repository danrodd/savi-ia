"""Tool MCP: información básica de la empresa actual desde el ERP.

Lectura segura del schema `Empresa.Empresa`. Solo los campos que un
usuario funcional querría ver (NIT, razón social, contacto, etc.).
La conexión usa el pool readonly del ERP con `default_transaction_read_only=on`
y `statement_timeout`, así que cualquier escritura accidental falla en el motor.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.infrastructure.database.pool import get_erp_engine

_SQL = """
SELECT
    "nit",
    "digitoVerificacion",
    "razonSocial",
    "direccion",
    "telefono",
    "celular",
    "email",
    "representanteLegal",
    "cargo"
FROM "Empresa"."Empresa"
ORDER BY "idEmpresa"
LIMIT 1
"""


async def info_empresa_impl(_args: dict[str, Any]) -> dict[str, Any]:
    try:
        engine = get_erp_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text(_SQL))
            row = result.mappings().first()
    except Exception as e:  # noqa: BLE001
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "No pude consultar la información de la empresa en este "
                        f"momento por un problema técnico: {e}"
                    ),
                }
            ],
            "isError": True,
        }

    if row is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Aún no hay una empresa configurada en el sistema. "
                        "Pídele al administrador que complete el registro inicial."
                    ),
                }
            ]
        }

    lines = ["Información de la empresa registrada en el sistema:"]
    fields: list[tuple[str, str]] = [
        ("NIT", _join_nit(row["nit"], row["digitoVerificacion"])),
        ("Razón social", row["razonSocial"] or "—"),
        ("Dirección", row["direccion"] or "—"),
        ("Teléfono", row["telefono"] or "—"),
        ("Celular", row["celular"] or "—"),
        ("Correo", row["email"] or "—"),
        ("Representante legal", row["representanteLegal"] or "—"),
        ("Cargo", row["cargo"] or "—"),
    ]
    for label, value in fields:
        lines.append(f"- {label}: {value}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def _join_nit(nit: Any, dv: Any) -> str:
    if not nit:
        return "—"
    return f"{nit}-{dv}" if dv else str(nit)
