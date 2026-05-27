from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolInvocationStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


@dataclass(slots=True)
class ToolInvocation:
    """Una invocación de tool dentro de un turno del asistente.

    Persistida como parte del mensaje del asistente (JSONB). Permite al
    frontend mostrar chips/spinners de tools en mensajes históricos y
    auditar qué consultó SAVI para construir cada respuesta.
    """

    id: str
    name: str
    input: dict[str, Any]
    status: ToolInvocationStatus = ToolInvocationStatus.RUNNING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolInvocation":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            input=dict(data.get("input") or {}),
            status=ToolInvocationStatus(data.get("status", "running")),
        )
