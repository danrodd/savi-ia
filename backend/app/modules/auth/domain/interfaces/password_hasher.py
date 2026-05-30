from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    """Hash de password contra el formato del origen de identidades.

    En la implementación actual, el ERP almacena las claves en MD5 sin
    salt — heredado del sistema legacy. El puerto está abstraído para
    que el día que el ERP migre a bcrypt/argon2 (o aparezca otro origen)
    solo cambie la implementación.
    """

    @abstractmethod
    def hash(self, password: str) -> str:
        """Devuelve el hash del password en el formato esperado por el origen."""

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        """¿Coincide el password plano con el hash almacenado?"""
