"""El texto que sigue a una tool no queda pegado al preámbulo.

Los modelos escriben "Déjame revisar los datos...", llaman a la tool y
siguen: sin separador, la respuesta salía como "...los datos...En 2025
facturaste", en pantalla y en el mensaje guardado.
"""

from __future__ import annotations

from app.modules.chat.application.use_cases.chat_turn import (
    _TurnAccumulator,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.chat.domain.entities import ChatEvent, TextDeltaEvent, ToolUseEvent


def _run(events: list[ChatEvent]) -> str:
    """Reproduce el loop del turno: separador (si toca) y después el evento."""
    acc = _TurnAccumulator()
    for event in events:
        separator = acc.separator_before(event)
        if separator is not None:
            acc.consume(separator)
        acc.consume(event)
    return "".join(acc.text_parts)


def _tool() -> ToolUseEvent:
    return ToolUseEvent(id="t1", name="consultar_datos", input={})


def test_text_after_a_tool_starts_a_new_paragraph() -> None:
    texto = _run(
        [TextDeltaEvent("Déjame revisar los datos..."), _tool(), TextDeltaEvent("En 2025")]
    )

    assert texto == "Déjame revisar los datos...\n\nEn 2025"


def test_no_separator_when_the_boundary_already_has_whitespace() -> None:
    assert _run([TextDeltaEvent("Reviso.\n"), _tool(), TextDeltaEvent("Listo")]) == "Reviso.\nListo"
    assert _run([TextDeltaEvent("Reviso."), _tool(), TextDeltaEvent(" Listo")]) == "Reviso. Listo"


def test_no_separator_when_the_turn_starts_with_a_tool() -> None:
    assert _run([_tool(), TextDeltaEvent("En 2025")]) == "En 2025"


def test_consecutive_deltas_without_a_tool_are_not_split() -> None:
    assert _run([TextDeltaEvent("En 20"), TextDeltaEvent("25")]) == "En 2025"


def test_several_tools_in_a_row_add_a_single_separator() -> None:
    texto = _run([TextDeltaEvent("Busco..."), _tool(), _tool(), TextDeltaEvent("Encontré")])

    assert texto == "Busco...\n\nEncontré"
