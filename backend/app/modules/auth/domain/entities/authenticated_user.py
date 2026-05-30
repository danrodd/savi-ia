"""Usuario autenticado — la representación de dominio del usuario actual.

Es **independiente** del schema del ERP (tabla `Seguridad.Usuario`): el
repositorio la construye traduciendo los campos. Si mañana el origen
cambia (otra fuente, otra app), las capas superiores no se enteran.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    # `idUsuario` del ERP. Tipo `int` porque en el schema es integer.
    id: int
    # `codigo` del usuario en el ERP (login). Se usa también como subject.
    login: str
    full_name: str
    is_admin: bool
    is_active: bool
