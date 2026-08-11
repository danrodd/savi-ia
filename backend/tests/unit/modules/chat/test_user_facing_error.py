"""Un error de credencial tiene que decir cómo salir de él.

El mensaje del SDK describe el problema ("401 OAuth access token has
expired") pero no qué hacer, y quien lo lee sólo quería preguntar por una
factura. Sin la línea agregada, el usuario queda sin salida dentro del
chat aunque el remedio sea un clic en el menú Inicio.
"""

from __future__ import annotations

import pytest

from app.modules.chat.infrastructure.llm.runner import _user_facing_error

_HINT = "Iniciar sesión en Claude"


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
