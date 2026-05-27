from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class TokenUsage:
    """Uso de tokens reportado por el SDK al cierre de un turno."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenUsage":
        return cls(
            input_tokens=int(data.get("input_tokens") or 0),
            output_tokens=int(data.get("output_tokens") or 0),
            cache_read_input_tokens=int(data.get("cache_read_input_tokens") or 0),
            cache_creation_input_tokens=int(
                data.get("cache_creation_input_tokens") or 0
            ),
        )
