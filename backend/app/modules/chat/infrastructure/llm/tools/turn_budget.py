"""Presupuesto de un turno: cuántas consultas al ERP y cuánto texto por tool.

En la demo del 2026-11-11 un turno hizo 14 consultas al ERP, cada una con su
tabla, y los turnos siguientes fallaron con OpenAI: todo eso vuelve a viajar al
modelo en cada iteración. El presupuesto corta antes:

- después de `max_queries` consultas, la siguiente no va a la base y le dice al
  modelo que responda con lo que tiene;
- el texto de una sola tool se recorta a `max_chars`, con un aviso que dice qué
  hacer en lugar de un corte mudo;
- después de dos rechazos por permiso, no se hacen más consultas en el turno.

Vive lo que dura el turno: lo arma `build_savi_tools`, que también es por turno.
"""

from __future__ import annotations

from app.modules.chat.domain.entities import ToolResult
from app.modules.data_query.application.permission_text import PERMISSION_DENIED_MARK

QUERY_LIMIT_MESSAGE = (
    "Llegaste al máximo de consultas al ERP de este turno ({limit}). No hagas más "
    "consultas: responde con los datos que ya tienes y dile al usuario qué parte "
    "no alcanzaste a revisar, para que la pida en otro mensaje."
)
DENIED_AGAIN_MESSAGE = (
    "Ya recibiste dos rechazos por permiso en este turno. No hagas más consultas: "
    "responde con lo que tienes y repite al usuario la frase de permiso que te dio "
    "la herramienta."
)
# Rechazos por permiso que se toleran en un turno antes de cortar las consultas.
MAX_PERMISSION_DENIALS = 2
CUT_NOTICE = (
    "\n\n_(Resultado recortado: era demasiado largo para seguir analizándolo. "
    "Pide un agregado (totales, conteos) o afina los filtros.)_"
)


class TurnBudget:
    def __init__(self, *, max_queries: int, max_chars: int) -> None:
        self._max_queries = max_queries
        self._max_chars = max_chars
        self.queries = 0
        self.denials = 0

    def take_query(self) -> ToolResult | None:
        """Cuenta una consulta al ERP; si ya no quedan, el resultado a devolver."""
        if self.denials >= MAX_PERMISSION_DENIALS:
            return ToolResult(text=DENIED_AGAIN_MESSAGE, is_error=True)
        if self.queries >= self._max_queries:
            return ToolResult(
                text=QUERY_LIMIT_MESSAGE.format(limit=self._max_queries), is_error=True
            )
        self.queries += 1
        return None

    def fit(self, result: ToolResult) -> ToolResult:
        # Cada rechazo por permiso cuenta para el corte: en la demo el modelo
        # insistió siete veces contra el mismo bloqueo.
        if PERMISSION_DENIED_MARK in result.text:
            self.denials += 1
        if len(result.text) <= self._max_chars:
            return result
        return ToolResult(
            text=result.text[: self._max_chars] + CUT_NOTICE, is_error=result.is_error
        )
