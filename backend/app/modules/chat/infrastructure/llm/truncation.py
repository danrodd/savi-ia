"""Límite de tamaño de la respuesta visible, común a todos los proveedores."""

from app.modules.chat.domain.entities import TextDeltaEvent

TRUNCATION_NOTICE = (
    "\n\n_(Respuesta truncada por límite de tamaño. Si necesitas más "
    "detalle, pídeme una sección específica.)_"
)


class ResponseTruncator:
    """Recorta el texto emitido a `max_chars` y agrega el aviso una sola vez.

    Solo afecta el texto visible: el loop de tools del turno sigue.
    """

    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars
        self._emitted = 0
        self._truncated = False

    @property
    def truncated(self) -> bool:
        return self._truncated

    def feed(self, text: str) -> list[TextDeltaEvent]:
        if self._truncated:
            return []
        remaining = self._max_chars - self._emitted
        if remaining <= 0:
            self._truncated = True
            return [TextDeltaEvent(text=TRUNCATION_NOTICE)]
        if len(text) > remaining:
            self._truncated = True
            self._emitted += remaining
            return [TextDeltaEvent(text=text[:remaining]), TextDeltaEvent(text=TRUNCATION_NOTICE)]
        self._emitted += len(text)
        return [TextDeltaEvent(text=text)]
