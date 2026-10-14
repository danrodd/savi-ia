from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager


class SyncLock(ABC):
    """Un sincronizador activo por BD (S8)."""

    @abstractmethod
    def acquire(self) -> AbstractAsyncContextManager[bool]:
        """Context manager que entrega `True` si este proceso tiene el turno
        y `False` si otro ya está sincronizando (el ciclo se omite)."""
