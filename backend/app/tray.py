"""Icono de SAVI en la bandeja del sistema.

SAVI se empaqueta con `console=False`: una vez arrancado no tiene ninguna
ventana, así que hasta ahora la única forma de cerrarlo era el
Administrador de tareas. Este icono le da las dos acciones que faltaban
—abrirlo y cerrarlo— y de paso le da al proceso un bucle de mensajes, que
es lo que el Restart Manager necesita para pedirle que se cierre solo
cuando el instalador actualiza sobre una instalación en ejecución.

Nunca puede impedir que SAVI sirva: `run()` se traga cualquier error y se
va en silencio. El icono es una comodidad; el servidor es el producto.
"""

# Los stubs de pywin32 no describen la API que realmente expone: `WNDCLASS`
# acepta asignación de atributos y `Shell_NotifyIcon` recibe una tupla —
# es la forma que usan los propios ejemplos del paquete, y está probada
# de punta a punta en este módulo. Se acalla acá y sólo acá; el resto del
# backend sigue en pyright strict.
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from typing import Protocol

log = logging.getLogger(__name__)

# WM_USER + 20. Windows manda acá los clics sobre el icono.
_WM_TRAY = 0x0400 + 20
_ID_OPEN = 1
_ID_QUIT = 2


class Stoppable(Protocol):
    """Lo único que hace falta de `uvicorn.Server` para poder cerrarlo."""

    should_exit: bool


def start(url: str, server: Stoppable) -> None:
    """Levanta el icono en su propio hilo.

    En hilo aparte porque el bucle de mensajes bloquea, y el hilo
    principal lo necesita uvicorn: sus manejadores de señales sólo se
    pueden instalar ahí.
    """
    threading.Thread(target=run, args=(url, server), daemon=True, name="savi-tray").start()


def run(url: str, server: Stoppable) -> None:
    """Bloquea hasta que alguien elige Salir. No propaga errores."""
    try:
        _run(url, server)
    except Exception:
        log.exception("No se pudo mostrar el icono de la bandeja.")


def _load_icon() -> int:
    """El icono que ya lleva embebido el ejecutable.

    Sacarlo de ahí y no de un `.ico` suelto garantiza que el de la
    bandeja sea el mismo que el del acceso directo, sin un archivo más
    que empaquetar y que se puede borrar.
    """
    import win32con
    import win32gui

    large, small = win32gui.ExtractIconEx(sys.executable, 0)
    chosen = (small or large or [None])[0]
    for handle in large + small:
        if handle != chosen:
            win32gui.DestroyIcon(handle)
    # Corriendo sin empaquetar, `python.exe` no trae icono propio.
    return chosen or win32gui.LoadIcon(0, win32con.IDI_APPLICATION)


def _run(url: str, server: Stoppable) -> None:
    if sys.platform != "win32":
        return

    import win32con
    import win32gui

    def quit_savi(hwnd: int) -> None:
        # El icono primero: si el proceso se va antes de sacarlo, Windows
        # deja el fantasma en la bandeja hasta que alguien le pasa el
        # mouse por encima.
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0))
        win32gui.PostQuitMessage(0)
        server.should_exit = True

    def show_menu(hwnd: int) -> None:
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, _ID_OPEN, "Abrir SAVI")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, _ID_QUIT, "Salir")
        x, y = win32gui.GetCursorPos()
        # SetForegroundWindow antes y WM_NULL después: sin ese par el menú
        # queda abierto cuando el usuario hace clic afuera.
        win32gui.SetForegroundWindow(hwnd)
        win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_BOTTOMALIGN,
            x,
            y,
            0,
            hwnd,
            None,
        )
        win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

    def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == _WM_TRAY:
            if lparam == win32con.WM_LBUTTONDBLCLK:
                webbrowser.open(url)
            elif lparam == win32con.WM_RBUTTONUP:
                show_menu(hwnd)
        elif msg == win32con.WM_COMMAND:
            command = wparam & 0xFFFF
            if command == _ID_OPEN:
                webbrowser.open(url)
            elif command == _ID_QUIT:
                quit_savi(hwnd)
        elif msg == win32con.WM_CLOSE:
            # Por acá entra el Restart Manager cuando el instalador
            # actualiza sobre una instalación en ejecución.
            quit_savi(hwnd)
        else:
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
        return 0

    window_class = win32gui.WNDCLASS()
    window_class.hInstance = win32gui.GetModuleHandle(None)
    window_class.lpszClassName = "SaviTray"
    window_class.lpfnWndProc = wnd_proc
    class_atom = win32gui.RegisterClass(window_class)

    # Ventana sin mostrar: existe sólo para recibir los mensajes del icono.
    hwnd = win32gui.CreateWindow(
        class_atom,
        "SAVI",
        win32con.WS_OVERLAPPED,
        0,
        0,
        0,
        0,
        0,
        0,
        window_class.hInstance,
        None,
    )
    win32gui.Shell_NotifyIcon(
        win32gui.NIM_ADD,
        (
            hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            _WM_TRAY,
            _load_icon(),
            f"SAVI — {url}",
        ),
    )
    log.info("Icono de la bandeja activo.")
    win32gui.PumpMessages()
