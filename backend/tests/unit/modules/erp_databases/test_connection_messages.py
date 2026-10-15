"""Los mensajes de la prueba de conexión: uno por caso, completos y sin
repeticiones.

La interfaz muestra `detail` tal cual (no le antepone nada), así que cada
texto tiene que bastarse solo y no empezar con una frase que otro nivel
ya agrega.
"""

from __future__ import annotations

import socket

import pytest

from app.modules.erp_databases.infrastructure.postgres_connection_tester import _explain


def _error(message: str) -> Exception:
    return Exception(message)


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (socket.gaierror(11001, "getaddrinfo failed"), "No encontramos ese servidor"),
        (_error("[Errno -2] Name or service not known"), "No encontramos ese servidor"),
        (_error("password authentication failed for user"), "Usuario o contraseña incorrectos"),
        (_error('database "x" does not exist'), "La base de datos no existe"),
        (TimeoutError("timed out"), "no respondió a tiempo"),
        (ConnectionRefusedError("Connect call failed, connection refused"), "aceptando conexiones"),
        (_error("algo raro"), "Revise los datos de conexión"),
    ],
)
def test_each_failure_has_its_own_single_sentence(error: Exception, fragment: str) -> None:
    detail = _explain(error)

    assert detail is not None
    assert fragment in detail
    assert detail.lower().count("no se pudo conectar") <= 1
    # Sin jerga de red que el formulario ya no usa como etiqueta.
    assert "host" not in detail.lower()


def test_ambiguous_driver_error_is_left_for_the_probe() -> None:
    assert _explain(_error("connection was closed in the middle of operation")) is None
