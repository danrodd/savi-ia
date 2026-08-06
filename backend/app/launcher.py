"""Punto de entrada del ejecutable de escritorio.

Diferencias con `uv run dev`, que es lo que usa el desarrollador:

- Resuelve el `.env` y las rutas relativas contra el directorio del .exe,
  no contra el cwd (que al hacer doble clic es cualquier cosa).
- Prepara el esquema de la BD solo, porque nadie va a correr `alembic`.
- Deja un log en disco: sin esto, un fallo en el equipo de un cliente no
  deja rastro que se pueda pedir por teléfono.
- Abre el navegador cuando el servidor ya responde.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.diagnostics import CheckResult, Report, now_label, render_html
from app.paths import data_dir, is_frozen

if TYPE_CHECKING:
    from app.infrastructure.config.settings import Settings

_LOG_FILENAME = "savi.log"
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUPS = 3


def app_dir() -> Path:
    """Directorio donde vive el ejecutable (o `backend/` en desarrollo)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _force_utf8_console() -> None:
    """Pone la consola de Windows en UTF-8.

    Windows abre las consolas en una codepage heredada (850 o 1252) y el
    texto en UTF-8 de los mensajes sale con caracteres rotos. El
    diagnóstico lo lee una persona de soporte: que se vea
    "Configuración" y no "Configuraci?n" no es cosmético, es la
    diferencia entre un reporte legible y uno que parece un error.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)  # type: ignore[attr-defined]
    except (ImportError, AttributeError, OSError):
        # Sin consola (por ejemplo, salida redirigida a un archivo) no hay
        # codepage que ajustar; el reconfigure de abajo alcanza.
        pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _ensure_console() -> None:
    """Habilita una consola visible para los modos interactivos.

    El build de escritorio compila sin consola (`console=False` en
    savi.spec) para no abrir una terminal en cada uso normal. Pero
    `--check-config` y `--login` son justo los modos pensados para leer
    texto en pantalla — sin esto `print()` no tiene a dónde escribir.

    También se reabre la entrada estándar: `--login` le pide al usuario
    que pegue un token, y el CLI de Claude hace sus propias preguntas.
    Sin `CONIN$` esas lecturas fallan con EOF apenas arrancan.

    Solo empaquetado: en desarrollo ya hay una consola y reemplazar los
    streams rompería el redireccionamiento a un archivo o a otro proceso.
    """
    if sys.platform != "win32" or not is_frozen():
        return
    import ctypes

    ctypes.windll.kernel32.AllocConsole()  # type: ignore[attr-defined]
    sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115 - vive todo el proceso
    sys.stderr = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
    sys.stdin = open("CONIN$", encoding="utf-8")  # noqa: SIM115


def _splash(text: str | None = None, *, close: bool = False) -> None:
    """Escribe el paso actual en la pantalla de arranque, o la cierra.

    `pyi_splash` solo existe dentro del ejecutable empaquetado con
    splash; en desarrollo y en los tests no está y esto es un no-op.

    Nada de lo que pase acá puede tumbar el arranque: la pantalla es
    cosmética y el usuario prefiere una app sin splash antes que una que
    no abre.
    """
    try:
        import pyi_splash  # type: ignore[import-not-found]
    except ImportError:
        return

    try:
        if close:
            pyi_splash.close()
        elif text is not None:
            pyi_splash.update_text(text)
    except Exception:  # noqa: BLE001 - ver docstring
        logging.getLogger(__name__).debug("No se pudo actualizar el splash.", exc_info=True)


def _show_fatal_error(message: str) -> None:
    """Único canal visible en el build sin consola.

    Sin esto, un fallo de arranque es una app que nunca abre y ninguna
    pista de por qué — peor que la terminal que reemplazó.
    """
    # Primero cerrar el splash: se dibuja siempre encima, y con él abierto
    # el cartel de error queda tapado — el usuario ve una pantalla de
    # carga congelada para siempre en vez del motivo del fallo.
    _splash(close=True)
    if sys.platform != "win32":
        return
    import ctypes

    full_message = (
        f"{message}\n\nDetalle completo en:\n{data_dir() / _LOG_FILENAME}\n\n"
        "Podés diagnosticar desde el acceso directo 'Diagnosticar SAVI'."
    )
    ctypes.windll.user32.MessageBoxW(0, full_message, "SAVI — Error de arranque", 0x10)  # type: ignore[attr-defined]


def _ensure_claude_cli_on_path() -> None:
    """Agrega al PATH los directorios donde npm deja el CLI de Claude.

    El SDK lanza el binario `claude` buscándolo en el PATH. El instalador
    lo instala con un prefijo común a la máquina y agrega esa ruta al
    PATH del sistema, pero un proceso que ya está corriendo no ve ese
    cambio hasta cerrar sesión — incluido el que arranca justo después de
    instalar. Reponerlo acá evita ese "funciona recién mañana".
    """
    program_data = os.environ.get("PROGRAMDATA")
    app_data = os.environ.get("APPDATA")
    candidates = [
        Path(program_data) / "npm" if program_data else None,
        Path(app_data) / "npm" if app_data else None,
    ]
    current = os.environ.get("PATH", "")
    known = {entry.lower() for entry in current.split(os.pathsep)}
    for candidate in candidates:
        if candidate is None or not candidate.is_dir():
            continue
        if str(candidate).lower() in known:
            continue
        current = f"{candidate}{os.pathsep}{current}"
    os.environ["PATH"] = current


def _hide_subprocess_consoles() -> None:
    """Evita que cada turno abra una ventana de terminal.

    El SDK lanza `claude.exe`, que es una aplicación de consola. SAVI se
    compila sin consola (`console=False`), así que el hijo no tiene
    ninguna a la que engancharse y Windows le crea una ventana propia:
    en pantalla aparece una terminal negra por cada turno del chat.

    El SDK no expone cómo lanza el proceso, pero llama a
    `anyio.open_process`, que sí acepta `creationflags`, y resuelve el
    atributo en cada llamada — por eso alcanza con reemplazarlo acá.

    Solo empaquetado: en desarrollo ya hay consola, el hijo se engancha a
    ella y ocultarla se llevaría puesta la salida del CLI.
    """
    if sys.platform != "win32" or not is_frozen():
        return

    import subprocess

    import anyio

    original = anyio.open_process

    async def open_process_without_window(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return await original(*args, **kwargs)

    anyio.open_process = open_process_without_window  # type: ignore[assignment]


def _configure_logging() -> None:
    """Deja el log en disco, acotado.

    Rotado y no `FileHandler` a secas: uvicorn corre con `log_config=None`,
    así que sus loggers propagan a este root y se registra una línea por
    cada petición HTTP. Sin límite, el archivo del equipo de un cliente
    activo llega a cientos de MB — y deja de servir justo cuando hace
    falta abrirlo para diagnosticar algo.

    Con estos valores quedan a lo sumo 20 MB y varios días de historia,
    que es el horizonte útil para un reporte de soporte.

    `force=True` porque `basicConfig` es un no-op silencioso si el root
    logger ya tiene handlers: bastaría con que una dependencia llamara a
    `basicConfig` al importarse para que el archivo nunca se creara, sin
    ningún error, y soporte se quedara sin log en el equipo del cliente.
    """
    logging.basicConfig(
        force=True,
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(
                data_dir() / _LOG_FILENAME,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUPS,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex((host, port)) != 0


def _savi_already_running(url: str) -> bool:
    """`True` si quien ocupa el puerto es otra instancia de SAVI.

    Hacer doble clic dos veces en el acceso directo es lo más normal del
    mundo; sin este chequeo la segunda vez el usuario ve un stacktrace de
    "address already in use".
    """
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
            return b'"status"' in response.read(200)
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _open_browser_when_ready(url: str) -> None:
    """Espera a que el servidor responda y recién ahí abre el navegador.

    Abrir con un `sleep` fijo muestra una pantalla de error cuando el
    arranque tarda más de lo previsto (equipo lento, antivirus).
    """
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1):
                _splash("Abriendo el navegador...")
                webbrowser.open(url)
                # Después del navegador: si se cierra antes, quedan unos
                # segundos de escritorio vacío sin nada que indique que
                # algo sigue pasando.
                _splash(close=True)
                return
        except (urllib.error.URLError, OSError, TimeoutError):
            threading.Event().wait(0.5)
    _splash(close=True)
    logging.getLogger(__name__).warning("El servidor no respondió a tiempo; abrí %s a mano.", url)


def _claude_auth_status(settings: Settings) -> str:
    """Cómo se va a autenticar el CLI `claude` que lanza el SDK.

    Mismo orden que el propio SDK: token de Claude Code, clave de API, o
    una sesión ya logueada en esta cuenta de Windows
    (`claude login`, guardada en `~/.claude/.credentials.json`). Ninguna
    de las tres es "la correcta" — el token es la preferida porque no
    depende de que el cliente administre una clave, pero cualquiera
    alcanza para que el agente responda.
    """
    if settings.claude_code_oauth_token:
        return "token de Claude Code"
    if settings.anthropic_api_key:
        return "clave de API de Anthropic"
    if (Path.home() / ".claude" / ".credentials.json").is_file():
        return "sesión local de Claude Code (claude login)"
    return ""


_OAUTH_TOKEN_KEY = "CLAUDE_CODE_OAUTH_TOKEN"


def replace_env_line(lines: list[str], key: str, value: str) -> list[str]:
    """Devuelve `lines` con `key=value`, respetando el resto del archivo.

    Se edita línea por línea en vez de reescribir el `.env` entero: el
    archivo lo generó el instalador con las contraseñas de las dos bases
    de datos, y regenerarlo desde la plantilla las perdería.

    Si la clave ya está, se reemplaza en su lugar (incluso comentada, que
    es como la deja la plantilla cuando no se cargó ningún token). Si no,
    se agrega al final.
    """
    prefixes = (f"{key}=", f"#{key}=", f"# {key}=")
    replacement = f"{key}={value}"
    updated: list[str] = []
    found = False

    for line in lines:
        if not found and line.strip().startswith(prefixes):
            # Se conserva el salto de línea original para no pegar esta
            # clave con la siguiente ni cambiar CRLF por LF.
            newline = line[len(line.rstrip("\r\n")) :]
            updated.append(replacement + newline)
            found = True
        else:
            updated.append(line)

    if not found:
        if updated and not updated[-1].endswith("\n"):
            updated[-1] += "\n"
        updated.append(replacement + "\n")

    return updated


def _write_oauth_token(token: str) -> bool:
    """Guarda el token en el `.env`. `False` si no se pudo escribir."""
    env_path = app_dir() / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as error:
        print(f"[FALLA] No se pudo leer {env_path}: {error}")
        return False

    try:
        env_path.write_text(
            "".join(replace_env_line(lines, _OAUTH_TOKEN_KEY, token)), encoding="utf-8"
        )
    except OSError as error:
        # El .env vive en Program Files: sin privilegios no se puede
        # escribir, y el mensaje del sistema por sí solo no dice qué hacer.
        print(f"[FALLA] No se pudo escribir {env_path}: {error}")
        print(
            "\nEse archivo está en una carpeta protegida de Windows. Cerrá esta "
            "ventana y volvé a abrir 'Iniciar sesión en Claude' con clic derecho "
            "> Ejecutar como administrador."
        )
        return False

    return True


def _claude_cli_path() -> str | None:
    import shutil

    return shutil.which("claude")


def _cli_reports_logged_in(claude: str) -> bool:
    """`True` si el propio CLI dice que hay sesión.

    Se le pregunta a `claude auth status` en vez de mirar el archivo de
    credenciales: dónde las guarda es asunto suyo y puede cambiar entre
    versiones. El archivo queda como respaldo por si el subcomando no
    existe en la versión instalada.
    """
    import subprocess

    try:
        completed = subprocess.run(  # noqa: S603 - ruta resuelta con shutil.which
            [claude, "auth", "status"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return (Path.home() / ".claude" / ".credentials.json").is_file()
    return completed.returncode == 0


def _login() -> int:
    """Deja a SAVI autenticado contra la cuenta de Claude del cliente.

    Dos caminos, y el orden importa:

    1. `claude auth login` — el cliente entra con su suscripción en el
       navegador y no hay nada que copiar. Es el caso normal.
    2. `claude setup-token` — si lo anterior no alcanzó. Imprime un token
       que se guarda en el `.env`, y por eso sobrevive a que SAVI corra
       con otra cuenta de Windows (un servicio, un servidor). Las
       credenciales del punto 1 viven en el perfil de quien hizo el login
       y esa cuenta no siempre es la que después usa la aplicación.
    """
    import subprocess

    claude = _claude_cli_path()
    if claude is None:
        print(
            "[FALLA] No se encontró el CLI de Claude en este equipo.\n\n"
            "Instalalo con:  npm install -g @anthropic-ai/claude-code\n"
            "y volvé a abrir 'Iniciar sesión en Claude'."
        )
        input("\nEnter para cerrar...")
        return 1

    print("=" * 62)
    print(" SAVI — Iniciar sesión en Claude")
    print("=" * 62)
    print(
        "\nSe va a abrir el navegador para que inicies sesión con tu cuenta\n"
        "de Claude (Pro o Max). Seguí los pasos que aparezcan ahí y volvé\n"
        "a esta ventana cuando termines.\n"
    )

    try:
        subprocess.run([claude, "auth", "login"], check=False)  # noqa: S603 - ruta de shutil.which
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[AVISO] No se pudo completar el inicio de sesión: {error}")

    if _cli_reports_logged_in(claude):
        print("\n[OK] Sesión iniciada. Ya podés usar SAVI.")
        print(
            "\nNota: la sesión queda guardada para esta cuenta de Windows. Si SAVI\n"
            "se va a usar desde otra cuenta o como servicio, elegí 'n' abajo y\n"
            "generá un token en su lugar."
        )
        if input("\n¿Terminaste? [S/n]: ").strip().lower() not in ("n", "no"):
            return 0

    print("\n" + "-" * 62)
    print("Vamos por el token de larga duración.")
    print(
        "\nSe va a abrir el navegador otra vez. Al final, el CLI va a mostrar\n"
        "un token largo en pantalla: copialo y pegalo acá abajo.\n"
    )

    try:
        subprocess.run([claude, "setup-token"], check=False)  # noqa: S603 - ruta de shutil.which
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[FALLA] No se pudo generar el token: {error}")
        input("\nEnter para cerrar...")
        return 1

    token = input("\nPegá el token acá y presioná Enter: ").strip()
    if not token:
        print("[FALLA] No se cargó ningún token. No se cambió nada.")
        input("\nEnter para cerrar...")
        return 1

    if not _write_oauth_token(token):
        input("\nEnter para cerrar...")
        return 1

    print(f"\n[OK] Token guardado en {app_dir() / '.env'}. Ya podés usar SAVI.")
    input("\nEnter para cerrar...")
    return 0


_RECONFIGURE_HINT = (
    "Volvé a ejecutar el instalador de SAVI y elegí 'Volver a configurar' para corregir los datos."
)


def _connection_remedy(label: str, error: Exception) -> str:
    """Traduce el error de conexión a algo accionable.

    Un `gaierror` crudo no le dice nada a quien está instalando; el nombre
    del servidor mal escrito, sí.
    """
    import socket

    if isinstance(error, socket.gaierror):
        return (
            f"No se pudo resolver el nombre del servidor de {label}. "
            f"Revisá que esté bien escrito y que este equipo lo alcance. " + _RECONFIGURE_HINT
        )
    if isinstance(error, (ConnectionRefusedError, TimeoutError, OSError)):
        return (
            f"El servidor de {label} no aceptó la conexión. Revisá el puerto, "
            f"que el servicio esté levantado y que el firewall lo permita. " + _RECONFIGURE_HINT
        )
    return f"Revisá los datos de conexión de {label}. " + _RECONFIGURE_HINT


def _collect_report() -> Report:
    """Corre todos los chequeos y devuelve el resultado como datos."""
    import asyncio

    from sqlalchemy import text

    from app.infrastructure.config import get_settings
    from app.infrastructure.database.pool import get_agent_engine, get_erp_engine, init_engines

    report = Report(env_path=str(app_dir() / ".env"), generated_at=now_label())

    try:
        settings = get_settings()
    except Exception as error:  # noqa: BLE001 - se reporta al usuario final
        report.results.append(
            CheckResult(
                label="Archivo de configuración",
                ok=False,
                detail=str(error)[:400],
                remedy="El archivo .env es inválido o le falta un valor obligatorio. "
                + _RECONFIGURE_HINT,
            )
        )
        return report

    report.results.append(
        CheckResult(
            label="Archivo de configuración",
            ok=True,
            detail=f"Válido. Base de datos de SAVI: {settings.agent_db_engine}.",
        )
    )

    async def probe() -> list[CheckResult]:
        init_engines(settings)
        checks: list[CheckResult] = []
        for label, engine in (
            ("la base de datos de SAVI", get_agent_engine()),
            ("la base de datos del ERP", get_erp_engine()),
        ):
            title = label[0].upper() + label[1:]
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                checks.append(CheckResult(label=title, ok=True, detail="Conexión correcta."))
            except Exception as error:  # noqa: BLE001 - se reporta al usuario final
                checks.append(
                    CheckResult(
                        label=title,
                        ok=False,
                        detail=f"{type(error).__name__}: {str(error)[:300]}",
                        remedy=_connection_remedy(label, error),
                    )
                )
        return checks

    report.results.extend(asyncio.run(probe()))

    auth_status = _claude_auth_status(settings)
    report.results.append(
        CheckResult(
            label="Autenticación de Claude",
            ok=bool(auth_status),
            detail=auth_status or "Este equipo no tiene ninguna forma de autenticarse.",
            remedy="Abrí el acceso directo 'Iniciar sesión en Claude' e iniciá sesión "
            "con la cuenta de Claude (Pro o Max) del cliente.",
        )
    )
    return report


def _check_config() -> int:
    """Valida el `.env` y la conectividad de las dos bases.

    Lo corre el instalador al terminar y queda como acceso directo
    "Diagnosticar SAVI": es lo primero que se le pide a un usuario que
    reporta que la aplicación no abre.

    Se muestra como página en el navegador y no en una consola: lo lee un
    técnico en el equipo de un cliente, y además así el reporte queda como
    archivo que se puede adjuntar a un pedido de soporte. La consola queda
    de respaldo para equipos sin navegador (un servidor, por ejemplo).
    """
    report = _collect_report()

    # Al log siempre, pase lo que pase con la presentación: si el técnico
    # cierra la ventana sin leerla, el reporte no se perdió.
    logging.getLogger(__name__).info("Diagnóstico:\n%s", report.as_text())

    destination = data_dir() / "diagnostico.html"
    try:
        destination.write_text(render_html(report), encoding="utf-8")
        opened = webbrowser.open(destination.as_uri())
    except (OSError, webbrowser.Error):
        opened = False

    if not opened:
        _ensure_console()
        _force_utf8_console()
        print(report.as_text())
        print(f"\n(No se pudo abrir el navegador; el reporte está en {destination})")
        input("\nEnter para cerrar...")

    return 1 if report.failures else 0


def main() -> None:
    # Antes que nada: el `.env` y cualquier ruta relativa se resuelven
    # contra el directorio de la app, no contra el cwd del doble clic.
    os.chdir(app_dir())
    interactive = {"--check-config", "--login"}.intersection(sys.argv)
    if interactive:
        # El splash se dibuja encima de todo: taparía tanto la consola
        # de --login como el reporte del navegador.
        _splash(close=True)
    if "--login" in sys.argv:
        _ensure_console()
    _force_utf8_console()
    _ensure_claude_cli_on_path()
    _hide_subprocess_consoles()
    _configure_logging()
    logger = logging.getLogger(__name__)

    if "--check-config" in sys.argv:
        raise SystemExit(_check_config())

    # Antes de tocar la configuración ni la base: iniciar sesión es lo que
    # se hace cuando SAVI todavía no arranca, así que no puede depender de
    # que el resto esté sano.
    if "--login" in sys.argv:
        raise SystemExit(_login())

    # Import diferido: `get_settings()` lee el `.env`, así que el chdir
    # tiene que haber ocurrido antes de que se importe la configuración.
    import uvicorn

    from app.infrastructure.config import get_settings
    from app.infrastructure.database.bootstrap import ensure_schema

    try:
        settings = get_settings()
    except Exception:
        logger.exception("Configuración inválida. Revisá el archivo .env en %s", app_dir())
        _show_fatal_error(
            f"El archivo .env es inválido o le falta un valor obligatorio.\n"
            f"Ubicación: {app_dir() / '.env'}"
        )
        raise SystemExit(1) from None

    host = settings.app_host
    port = settings.app_port
    # Para abrir el navegador, 0.0.0.0 no es una dirección conectable.
    browse_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browse_host}:{port}"

    if not _port_is_free(browse_host, port):
        if _savi_already_running(url):
            logger.info("SAVI ya estaba corriendo en %s; abriendo el navegador.", url)
            _splash(close=True)
            webbrowser.open(url)
            return
        logger.error(
            "El puerto %s está ocupado por otra aplicación. "
            "Cambiá APP_PORT en el archivo .env de %s y volvé a intentar.",
            port,
            app_dir(),
        )
        _show_fatal_error(
            f"El puerto {port} está ocupado por otra aplicación.\n"
            "Cambiá APP_PORT en el archivo .env y volvé a intentar."
        )
        raise SystemExit(1)

    _splash("Preparando la base de datos...")
    logger.info("Preparando la base de datos (%s).", settings.agent_db_engine)
    try:
        ensure_schema(settings)
    except Exception:
        logger.exception("No se pudo preparar la base de datos de SAVI.")
        _show_fatal_error(
            "No se pudo preparar la base de datos de SAVI.\n"
            "Revisá la conexión configurada en el archivo .env."
        )
        raise SystemExit(1) from None

    _splash("Iniciando el servidor...")

    # `--no-browser` para arranque desatendido y para probar el bundle sin
    # abrirle una ventana a nadie.
    if "--no-browser" not in sys.argv:
        # El hilo también cierra el splash: `uvicorn.run()` bloquea, así
        # que desde acá no hay forma de saber cuándo está listo.
        threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    else:
        _splash(close=True)

    logger.info("SAVI escuchando en %s", url)
    # Se pasa el objeto y no el string "app.main:app": empaquetado, la
    # resolución por import string depende del cwd y falla.
    # Sin --reload: el módulo chat lanza el binario claude como subproceso
    # y monta un MCP server in-process por turno.
    from app.main import app as fastapi_app

    uvicorn.run(fastapi_app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    main()
