"""`ConversationOwner` — la identidad completa del dueño de un hilo.

Existe para que las dos mitades no se puedan separar por descuido. El
`idUsuario` del ERP **no es único entre bases de clientes**: el usuario 5
del cliente A y el 5 del cliente B son personas distintas. Comparar solo
el entero deja ver las conversaciones de una a la otra.

Pasar un objeto en vez de dos parámetros sueltos hace que "olvidarse la
base" sea un error de tipos y no un cruce de datos silencioso.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConversationOwner:
    user_id: int
    # Base de IDENTIDAD (con la que se inició sesión), NO la base que la
    # conversación consulta — esas son cosas distintas desde D10 (un
    # usuario puede tener conversaciones de varios clientes a la vez).
    # `owns()` debe compararse siempre contra
    # `Conversation.owner_erp_database_id`.
    erp_database_id: UUID

    def owns(self, user_id: int | None, owner_erp_database_id: UUID | None) -> bool:
        """`True` si esta identidad es dueña de esos valores.

        Una conversación sin base de identidad (anterior al multi-BD)
        **no** pertenece a nadie bajo esta regla: no se puede saber de
        qué identidad era, y atribuirla a la base actual es justamente
        el cruce que se evita. Queda invisible en vez de ser accesible
        por la persona equivocada.
        """
        if user_id is None or owner_erp_database_id is None:
            return False
        return self.user_id == user_id and self.erp_database_id == owner_erp_database_id
