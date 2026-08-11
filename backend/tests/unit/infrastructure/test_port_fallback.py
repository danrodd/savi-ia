"""El puerto 8000 es de los más disputados que hay.

Antes, encontrarlo ocupado abortaba el arranque con la instrucción de
editar un archivo en Program Files — que pide administrador y que el
usuario final no va a tocar. Ahora se busca el siguiente libre.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from app.launcher import _port_is_free, _resolve_port

_HOST = "127.0.0.1"


@pytest.fixture
def occupied_port() -> Iterator[int]:
    """Un puerto realmente tomado por otro socket de este proceso."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind((_HOST, 0))
        taken.listen(1)
        yield taken.getsockname()[1]


def test_prefers_the_configured_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((_HOST, 0))
        free = probe.getsockname()[1]
    # El socket ya se cerró, así que `free` quedó disponible.
    assert _resolve_port(_HOST, free) == free


def test_skips_an_occupied_port(occupied_port: int) -> None:
    resolved = _resolve_port(_HOST, occupied_port)

    assert resolved is not None
    assert resolved != occupied_port, "no puede devolver el puerto que está tomado"
    assert _port_is_free(_HOST, resolved)


def test_returns_none_when_the_whole_range_is_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin esto el launcher arrancaría creyendo que consiguió un puerto.

    Devolver `None` es lo que dispara el cartel de error, que es el
    comportamiento correcto cuando de verdad no hay lugar.
    """
    monkeypatch.setattr("app.launcher._port_is_free", lambda _host, _port: False)

    assert _resolve_port(_HOST, 8000) is None
