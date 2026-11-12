"""El rechazo por permiso, con un texto fijo para el usuario.

En la demo el modelo insistió 7 veces contra el bloqueo y lo explicó distinto
cada vez ("no están disponibles", "no existen", "el sistema los protege"). El
rechazo ahora dice qué hacer y trae la frase exacta para el usuario.
"""

from __future__ import annotations

_MODULE_LABELS = {
    "TERCERO": "Terceros",
    "CUENTAPAGAR": "Cuentas por pagar",
    "CUENTACOBRAR": "Cuentas por cobrar",
    "INVENTARIO": "Inventario",
    "NÓMINA": "Nómina",
}

# Marca para reconocer el rechazo en el corte por turno (`TurnBudget`).
PERMISSION_DENIED_MARK = "[SIN_PERMISO]"


def user_message(modules: tuple[str, ...]) -> str:
    labels = " o ".join(_MODULE_LABELS.get(m, m.title()) for m in modules) or "ese módulo"
    return (
        f"Para ver esos datos necesita permiso en el módulo {labels} del ERP. "
        "Pídaselo al administrador del ERP."
    )


def permission_denied_text(denied: dict[str, tuple[str, ...]]) -> str:
    modules = tuple(dict.fromkeys(m for required in denied.values() for m in required))
    names = ", ".join(denied)
    return (
        f"{PERMISSION_DENIED_MARK} El usuario no tiene permiso para ver: {names}. "
        "NO vuelvas a intentarlo con otra consulta ni lo busques por otro camino. "
        "Responde con lo que sí puedas entregar sin esos datos y dile al usuario "
        f'exactamente esto: "{user_message(modules)}"'
    )
