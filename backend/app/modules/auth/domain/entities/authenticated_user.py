"""Usuario autenticado — la representación de dominio del usuario actual.

Es **independiente** del schema del ERP (tabla `Seguridad.Usuario`): el
repositorio la construye traduciendo los campos. Si mañana el origen
cambia (otra fuente, otra app), las capas superiores no se enteran.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    # `idUsuario` del ERP. Tipo `int` porque en el schema es integer.
    #
    # **NO es único entre bases.** El `idUsuario` 5 del cliente A y el 5
    # del cliente B son personas distintas. La identidad real de un
    # usuario en SAVI es el par `(erp_database_id, id)`: usar solo `id`
    # para filtrar conversaciones o consumo cruza datos entre clientes.
    id: int
    # `codigo` del usuario en el ERP (login). Se usa también como subject.
    login: str
    full_name: str
    is_admin: bool
    is_active: bool
    # Base del ERP donde vive esta identidad. Es la mitad que falta para
    # que `id` sea único. `None` solo en construcciones internas previas
    # a la resolución (nunca en un usuario autenticado real).
    erp_database_id: UUID | None = None
    # Módulos del ERP a los que el usuario tiene acceso. Se resuelve en
    # el caso de uso ResolveUserModules combinando is_admin + permisos
    # individuales + plan contratado. Vacío si todavía no se resolvió
    # (p. ej. justo después del login antes del bootstrap).
    modules: frozenset[ModuleCode] = field(default_factory=lambda: frozenset[ModuleCode]())
