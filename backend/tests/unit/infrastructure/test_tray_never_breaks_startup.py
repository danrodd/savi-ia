"""El icono de la bandeja no puede impedir que SAVI sirva.

SAVI corre sin ventana: el icono es la única forma de cerrarlo, pero es
una comodidad. Si el icono explota —win32 ausente, la clase de ventana ya
registrada, un equipo sin bandeja— el servidor tiene que arrancar igual.
Que el error se propague dejaría al cliente sin aplicación por culpa de
un adorno.
"""

from __future__ import annotations

import pytest

from app import tray


class _FakeServer:
    def __init__(self) -> None:
        self.should_exit = False


def test_run_swallows_any_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(url: str, server: object) -> None:
        raise RuntimeError("win32 no está disponible")

    monkeypatch.setattr(tray, "_run", explode)

    tray.run("http://127.0.0.1:31900", _FakeServer())  # no debe levantar


def test_start_returns_even_if_the_icon_dies(monkeypatch: pytest.MonkeyPatch) -> None:
    """`start()` arranca un hilo: main() sigue de largo hacia uvicorn."""

    def explode(url: str, server: object) -> None:
        raise RuntimeError("win32 no está disponible")

    monkeypatch.setattr(tray, "_run", explode)

    tray.start("http://127.0.0.1:31900", _FakeServer())
