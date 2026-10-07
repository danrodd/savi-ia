"""Imagen que viaja al modelo en un turno."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImageInput:
    mime: str
    data: bytes
    filename: str
    # `True`: adjunta al mensaje que se está respondiendo. `False`: viene de
    # un mensaje anterior de la conversación (contexto).
    from_current_turn: bool

    @property
    def label(self) -> str:
        """Texto que precede a la imagen para que el modelo sepa de cuál es."""
        origin = (
            "Imagen adjunta en este mensaje"
            if self.from_current_turn
            else "Imagen de un mensaje anterior"
        )
        return f"{origin}: {self.filename}"
