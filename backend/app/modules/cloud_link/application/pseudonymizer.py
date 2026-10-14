"""Seudónimos de usuario (S5).

`user_ref = hex(HMAC-SHA256(pseudonym_key, f"{erp_database_id}:{user_id}"))[:32]`.
La clave no sale nunca de la instancia: Cloud cuenta y distingue usuarios sin
poder saber quiénes son. El `idUsuario` se repite entre bases, por eso el par.
"""

import hashlib
import hmac
from uuid import UUID

from app.modules.cloud_link.domain.interfaces import CloudLinkRepository

_REF_LENGTH = 32


class Pseudonymizer:
    def __init__(self, key: bytes) -> None:
        if len(key) < 16:
            raise ValueError("La clave de seudónimos es demasiado corta.")
        self._key = key

    def user_ref(self, erp_database_id: UUID | None, user_id: int | None) -> str:
        # Una conversación anterior a auth no tiene base ni usuario: todas
        # comparten el mismo seudónimo "desconocido", estable entre ciclos.
        database = str(erp_database_id) if erp_database_id is not None else "none"
        user = str(user_id) if user_id is not None else "none"
        digest = hmac.new(self._key, f"{database}:{user}".encode(), hashlib.sha256).hexdigest()
        return digest[:_REF_LENGTH]


class PseudonymizerProvider:
    """Entrega el `Pseudonymizer` con la clave de la instancia.

    La clave se lee una vez por proceso: no cambia mientras corre (se genera
    antes de la primera vinculación y se conserva al desvincular).
    """

    def __init__(self, repository: CloudLinkRepository) -> None:
        self._repository = repository
        self._cached: Pseudonymizer | None = None

    async def get(self) -> Pseudonymizer:
        if self._cached is None:
            state = await self._repository.get()
            self._cached = Pseudonymizer(state.pseudonym_key)
        return self._cached
