"""Hasher MD5 — heredado del schema del ERP legacy.

⚠️ MD5 sin salt **no es seguro** para almacenar passwords. Lo usamos
solo para compatibilidad con el origen de identidades existente. Cuando
el cliente migre a bcrypt/argon2 en el ERP, basta con cambiar la impl
del puerto. NO se generan hashes nuevos desde SAVI — solo se verifican
contra los del ERP.

Comparación con `hmac.compare_digest` para evitar timing attacks (aunque
con MD5 sin salt es marginal, mantenemos la disciplina).
"""
from __future__ import annotations

import hashlib
import hmac

from app.modules.auth.domain.interfaces import PasswordHasher


class Md5PasswordHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return hashlib.md5(password.encode("utf-8"), usedforsecurity=False).hexdigest()

    def verify(self, password: str, hashed: str) -> bool:
        computed = self.hash(password)
        return hmac.compare_digest(computed.lower(), hashed.lower())
