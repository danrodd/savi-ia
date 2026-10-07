"""Un error de credencial tiene que decir cómo salir de él.

El mensaje del SDK describe el problema ("401 OAuth access token has
expired") pero no qué hacer, y quien lo lee sólo quería preguntar por una
factura. Sin la línea agregada, el usuario queda sin salida dentro del
chat aunque el remedio sea un clic en el menú Inicio.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock

from app.infrastructure.config import Settings
from app.modules.chat.domain.entities.chat_event import ErrorEvent
from app.modules.chat.domain.interfaces.active_provider import ActiveProvider
from app.modules.chat.infrastructure.llm.claude import runner as claude_runner
from app.modules.chat.infrastructure.llm.claude.runner import (
    CREDENTIAL_REMEDY,
    provider_error_message,
)
from app.modules.chat.infrastructure.llm.errors import user_facing_error

_HINT = "Iniciar sesión en Claude"


def _user_facing_error(message: str) -> str:
    return user_facing_error(message, credential_remedy=CREDENTIAL_REMEDY)


@pytest.mark.parametrize(
    "message",
    [
        "Failed to authenticate. API Error: 401 OAuth access token has expired.",
        "API Error: 401 Unauthorized",
        "invalid x-api-key",
        "OAuth token revoked",
    ],
)
def test_adds_the_way_out_for_credential_errors(message: str) -> None:
    result = _user_facing_error(message)

    assert _HINT in result
    # El mensaje original se conserva: soporte lo necesita textual.
    assert message in result


@pytest.mark.parametrize(
    "message",
    [
        "no existe la relación «Empresa.Tercero»",
        "Command failed: statement timeout",
        "La consulta es muy amplia: el planner estima ~40.000 filas",
        # Un 401 que no tiene nada que ver con credenciales.
        "La consulta devolvió 401 filas y el máximo es 50",
    ],
)
def test_leaves_other_errors_alone(message: str) -> None:
    """Sugerir renovar la credencial ante un error de SQL manda a la
    persona a perder el tiempo en el lugar equivocado."""
    assert _user_facing_error(message) == message


# ── Rechazos del proveedor que el CLI de Claude manda como texto ─────────


def test_an_exhausted_balance_says_what_to_do_in_spanish() -> None:
    message = provider_error_message("billing_error", "Credit balance is too low")

    assert message is not None
    assert "no tiene créditos" in message and "Credit balance" not in message


def test_a_normal_message_is_not_an_error() -> None:
    assert provider_error_message(None, "Hola, ¿en qué te ayudo?") is None


def test_an_unknown_error_keeps_the_detail_for_support() -> None:
    message = provider_error_message("server_error", "Overloaded")

    assert message is not None and "Overloaded" in message


async def test_the_runner_does_not_stream_the_rejection_as_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejected = AssistantMessage(
        content=[TextBlock(text="Credit balance is too low")],
        model="claude-sonnet-5",
        error="billing_error",
    )

    async def fake_stream(
        _prompt: str, _options: object, _images: object = ()
    ) -> AsyncIterator[object]:
        yield rejected

    monkeypatch.setattr(claude_runner, "_build_options", lambda *a, **k: None)
    monkeypatch.setattr(claude_runner, "_open_query_stream", fake_stream)
    provider = ActiveProvider(
        kind="claude", chat_model="m", title_model="t", credential_kind="api_key", credential="k"
    )
    runner = claude_runner.ClaudeAgentRunner(Settings(), provider)

    events = [event async for event in runner.stream_turn("hola")]

    assert [type(event) for event in events] == [ErrorEvent]
    assert "no tiene créditos" in cast(ErrorEvent, events[0]).message
