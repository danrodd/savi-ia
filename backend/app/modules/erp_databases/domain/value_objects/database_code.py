"""`DatabaseCode` — identificador corto de un cliente del ERP.

Es lo que el usuario escribe después del `@` al iniciar sesión
(`JPEREZ@NORTE`). El charset excluye el `@` por construcción, así que el
`rsplit("@", 1)` del login nunca puede volverse ambiguo.
"""
from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(r"^[A-Z0-9_-]{2,32}$")

MAX_LENGTH = 32


class InvalidDatabaseCodeError(ValueError):
    """El código no cumple el formato. La capa HTTP la mapea a 422."""


def normalize_code(raw: Any) -> str:
    """Normaliza y valida un código de cliente.

    Se normaliza a mayúsculas igual que `LoginUseCase` hace con el
    `codigo` del ERP: el usuario escribe `norte` y el ERP guarda `NORTE`.
    Sin esta normalización, `JPEREZ@norte` no resolvería.
    """
    if not isinstance(raw, str):
        raise InvalidDatabaseCodeError("El código del cliente debe ser texto.")
    code = raw.strip().upper()
    if not _PATTERN.match(code):
        raise InvalidDatabaseCodeError(
            "El código del cliente debe tener entre 2 y 32 caracteres y usar "
            "solo letras, números, guion y guion bajo (sin espacios ni '@')."
        )
    return code
