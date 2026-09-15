from abc import ABC, abstractmethod
from collections.abc import Sequence


class Embedder(ABC):
    """Vectorizador local. CPU-bound: se invoca desde un executor dedicado."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...
