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
import time
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
# Cuánto se le da a una instancia que está arrancando para contestar
# /health antes de concluir que el puerto lo tiene otra aplicación.
_HEALTH_GRACE_S = 8.0
# Lo que espera "Salir" a que terminen los turnos en curso antes de cortar.
_SHUTDOWN_GRACE_S = 10
# Puertos consecutivos a probar desde el configurado.
_PORT_SCAN_RANGE = 20
# Codigos de salida de --check-config. El instalador los distingue para
# dar la instruccion correcta segun QUE fallo.
_EXIT_CONFIG_PROBLEM = 1
_EXIT_AUTH_PROBLEM = 2
_EXIT_BOTH_PROBLEMS = 3


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


def _node_directory() -> Path | None:
    """Directorio donde vive `node.exe`, o `None` si no está instalado.

    Mismo orden que usa el instalador: primero el registro (vista de 64
    bits, que es donde escribe el MSI de Node), después las dos carpetas
    de Program Files.
    """
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Node.js",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                install_path = Path(str(winreg.QueryValueEx(key, "InstallPath")[0]))
            if (install_path / "node.exe").is_file():
                return install_path
        except (ImportError, OSError):
            pass

    for base in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(base)
        if root and (Path(root) / "nodejs" / "node.exe").is_file():
            return Path(root) / "nodejs"
    return None


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
        # Node.js también, no solo npm: el CLI instalado con npm es un
        # `claude.cmd` que invoca `node`. Si el directorio de Node no está
        # en el PATH de ESTE proceso, el shim arranca y falla solo, con un
        # mensaje del sistema operativo que no menciona a SAVI ni a Node
        # y no deja rastro de qué faltaba.
        _node_directory(),
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

    Se reintenta unos segundos en vez de preguntar una sola vez: uvicorn
    reserva el puerto antes de terminar de levantar la aplicación (cargar
    el catálogo, preparar la base), y en esa ventana `/health` todavía no
    contesta. Con un solo intento corto, la segunda instancia concluía
    que el puerto lo tenía un extraño y mostraba un error de puerto
    ocupado sobre la instancia propia que estaba arrancando bien.
    """
    deadline = time.monotonic() + _HEALTH_GRACE_S
    while True:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                return b'"status"' in response.read(200)
        except (urllib.error.URLError, OSError, TimeoutError):
            if time.monotonic() >= deadline:
                return False
            threading.Event().wait(0.5)


def _resolve_port(host: str, preferred: int) -> int | None:
    """Devuelve un puerto libre, o `None` si no hay ninguno en el rango.

    Prefiere el configurado. Si lo tiene otra aplicación, sigue con los
    siguientes en vez de abortar: el 8000 es de los puertos más
    disputados que existe, y hasta ahora el único remedio era editar el
    `.env` — un archivo en Program Files, que pide administrador y que el
    usuario final no va a tocar. Falla la aplicación entera por algo que
    se resuelve solo.

    No importa que el número cambie: al acceso directo lo abre el
    launcher, que arranca el navegador en la URL correcta. Nadie escribe
    el puerto a mano.
    """
    for candidate in range(preferred, preferred + _PORT_SCAN_RANGE):
        if _port_is_free(host, candidate):
            return candidate
    return None


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
    # La misma resolución que usa el runner: si el diagnóstico probara una
    # ruta distinta de la que el chat termina lanzando, volvería a salir en
    # verde junto a un chat roto.
    from app.infrastructure.claude_cli import resolve_cli_path

    return resolve_cli_path()


def _cli_probe(claude: str) -> tuple[bool, str]:
    """Corre `claude --version` y devuelve si anduvo y qué dijo.

    Que el archivo exista no significa que se pueda ejecutar: el CLI
    instalado con npm es un script que invoca `node`, y sin Node arranca y
    falla solo. Estar instalado y estar usable son cosas distintas, y
    hasta ahora sólo se chequeaba lo primero.
    """
    import subprocess

    try:
        completed = subprocess.run(  # noqa: S603 - ruta resuelta con shutil.which
            [claude, "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"{type(error).__name__}: {error}"

    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode == 0:
        return True, output.splitlines()[0] if output else "sin versión reportada"
    return False, output or f"terminó con código {completed.returncode} y sin mensaje"


def _cli_runs(claude: str) -> bool:
    ok, detail = _cli_probe(claude)
    print(f"Prueba:        {'OK — ' if ok else 'FALLA — '}{detail}")
    return ok


def _auth_probe(claude: str) -> tuple[bool, str]:
    """Le hace una pregunta trivial al modelo y devuelve si contestó.

    Es el único chequeo honesto de la autenticación. `claude auth status`
    devuelve `loggedIn: true` y código 0 **con el token de acceso
    vencido**: informa qué credencial hay guardada, no si sirve. El
    síntoma era un diagnóstico en verde junto a un chat que fallaba con
    "401 OAuth access token has expired".

    Cuesta una consulta mínima de la cuota del cliente. Es a pedido, y es
    la diferencia entre un reporte que da confianza y uno que miente.
    """
    import subprocess

    try:
        completed = subprocess.run(  # noqa: S603 - ruta resuelta con shutil.which
            [claude, "-p", "Responde unicamente: ok", "--max-turns", "1"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "el CLI no respondió en 2 minutos"
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"{type(error).__name__}: {error}"

    if completed.returncode == 0:
        return True, "el modelo respondió correctamente a una consulta de prueba"

    message = (completed.stderr or completed.stdout).strip()
    # Sólo la primera línea útil: el CLI a veces escupe un stack largo y
    # el reporte lo lee una persona, no un parser.
    first = next((line for line in message.splitlines() if line.strip()), "")
    return False, first or f"terminó con código {completed.returncode} y sin mensaje"


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
    # Qué se va a ejecutar y con qué. Sin esto, cuando el CLI falla por su
    # cuenta el usuario ve un mensaje del sistema operativo sin contexto
    # —"no se puede encontrar la ruta especificada"— y no hay forma de
    # saber qué ruta ni qué faltaba.
    print(f"\nCLI de Claude: {claude}")
    node = _node_directory()
    print(f"Node.js:       {node or 'NO ENCONTRADO'}")
    if node is None:
        print(
            "\n[AVISO] No se encontró Node.js. El CLI instalado con npm es un\n"
            "        script que lo necesita: sin Node, falla con un error del\n"
            "        sistema que no menciona ni a SAVI ni a Node.\n"
            "        Instalalo desde https://nodejs.org/ y volvé a intentar."
        )
    if not _cli_runs(claude):
        print(
            "\n[FALLA] El CLI de Claude está instalado pero no se puede ejecutar.\n"
            "        El detalle está arriba. Suele ser Node.js faltante o una\n"
            "        instalación del CLI a medio hacer; reinstalalo con:\n"
            "        npm install -g @anthropic-ai/claude-code"
        )
        input("\nEnter para cerrar...")
        return 1

    print(
        "\nSe va a abrir el navegador para que inicies sesión con tu cuenta\n"
        "de Claude (Pro o Max). Seguí los pasos que aparezcan ahí y volvé\n"
        "a esta ventana cuando termines.\n"
        "\nOjo: la sesión de la aplicación Claude Desktop NO sirve acá. El\n"
        "CLI guarda sus credenciales aparte y necesita su propio inicio de\n"
        "sesión, aunque sea la misma cuenta.\n"
    )

    try:
        subprocess.run([claude, "auth", "login"], check=False)  # noqa: S603 - ruta de shutil.which
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[AVISO] No se pudo completar el inicio de sesión: {error}")

    print("\nVerificando con una consulta de prueba (puede tardar unos segundos)...")
    logged_in, probe_detail = _auth_probe(claude)
    if logged_in:
        print("\n[OK] Sesión iniciada y verificada. Ya podés usar SAVI.")
        print(
            "\nNota: la sesión queda guardada para esta cuenta de Windows. Si SAVI\n"
            "se va a usar desde otra cuenta o como servicio, elegí 'n' abajo y\n"
            "generá un token en su lugar."
        )
        if input("\n¿Terminaste? [S/n]: ").strip().lower() not in ("n", "no"):
            return 0
    else:
        # Se distingue "no hay sesión" de "hay una sesión que no sirve".
        # Con el token vencido, `claude auth status` dice que todo bien y
        # el usuario no entiende por qué el chat falla.
        print(f"\n[FALLA] La sesión no quedó usable: {probe_detail}")

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
    from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

    from app.infrastructure.config import get_settings
    from app.infrastructure.database.pool import get_agent_engine, init_engines
    from app.modules.erp_databases.infrastructure.seed import (
        erp_database_from_settings,
        has_seed_config,
    )

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

        # El ERP del `.env` se chequea armando un engine descartable: es un
        # diagnóstico previo al arranque, y el registry de engines por
        # cliente todavía no existe en este punto. Con el `.env` vacío ya
        # no es un error — las bases se pueden registrar después desde la
        # sección de administración.
        probes: list[tuple[str, AsyncEngine]] = [
            ("la base de datos de SAVI", get_agent_engine())
        ]
        erp_engine: AsyncEngine | None = None
        if has_seed_config(settings):
            erp_engine = create_async_engine(
                erp_database_from_settings(settings).url,
                echo=False,
                pool_pre_ping=True,
            )
            probes.append(("la base de datos del ERP", erp_engine))

        for label, engine in probes:
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
        if erp_engine is not None:
            await erp_engine.dispose()
        return checks

    report.results.extend(asyncio.run(probe()))

    # El puerto se chequea acá porque su ausencia era engañosa: el reporte
    # decía "Todo en orden" mientras el arranque fallaba con "puerto
    # ocupado", y el técnico se quedaba sin saber a quién creerle.
    browse_host = "127.0.0.1" if settings.app_host in ("0.0.0.0", "::") else settings.app_host
    if _port_is_free(browse_host, settings.app_port):
        port_detail = f"El puerto {settings.app_port} está libre."
        port_ok = True
    elif _savi_already_running(f"http://{browse_host}:{settings.app_port}"):
        port_detail = f"SAVI ya está corriendo en el puerto {settings.app_port}."
        port_ok = True
    else:
        fallback = _resolve_port(browse_host, settings.app_port + 1)
        port_ok = fallback is not None
        port_detail = (
            f"El puerto {settings.app_port} lo tiene otra aplicación; SAVI va a usar el {fallback}."
            if port_ok
            else f"El puerto {settings.app_port} está ocupado y no hay ninguno "
            f"libre en los {_PORT_SCAN_RANGE} siguientes."
        )
    report.results.append(
        CheckResult(
            label="Puerto local",
            ok=port_ok,
            detail=port_detail,
            remedy="Cerrá la aplicación que está usando esos puertos, o cambiá "
            "APP_PORT en el archivo .env.",
        )
    )

    # Que el CLI se pueda EJECUTAR, no sólo que el archivo exista. El
    # reporte decía "sesión local de Claude Code" y daba todo por bueno
    # mientras el chat fallaba con "Command failed with exit code 1",
    # porque el CLI arrancaba y moría sin poder encontrar Node.
    claude_path = _claude_cli_path()
    if claude_path is None:
        report.results.append(
            CheckResult(
                label="CLI de Claude",
                ok=False,
                detail="No está instalado en este equipo.",
                remedy=(
                    "Volvé a correr el instalador de SAVI: instala el CLI "
                    "de Claude y todo lo que necesita."
                ),
            )
        )
    else:
        runs, detail = _cli_probe(claude_path)
        report.results.append(
            CheckResult(
                label="CLI de Claude",
                ok=runs,
                detail=f"{claude_path} — {detail}",
                # A mano también funciona —`npm install -g` vuelve a
                # correr el postinstall que baja el binario aunque el
                # paquete ya esté, comprobado—, pero exige una terminal
                # elevada y acertar con el prefijo global. El instalador
                # hace las dos cosas sin pedirle nada a quien lo corre.
                remedy=(
                    "El CLI quedó a medio instalar y le falta su binario. "
                    "Volvé a correr el instalador de SAVI: detecta el CLI "
                    "roto y lo reinstala."
                ),
            )
        )

    # La autenticación se PRUEBA con una consulta real, no se deduce de que
    # haya una credencial guardada: `claude auth status` devuelve
    # loggedIn:true y código 0 con el token de acceso vencido, así que el
    # reporte salía en verde mientras el chat fallaba con 401.
    auth_status = _claude_auth_status(settings)
    if claude_path is None or not auth_status:
        report.results.append(
            CheckResult(
                label="Autenticación de Claude",
                ok=False,
                detail=auth_status or "Este equipo no tiene ninguna forma de autenticarse.",
                remedy="Abrí el acceso directo 'Iniciar sesión en Claude' e iniciá sesión "
                "con la cuenta de Claude (Pro o Max) del cliente.",
            )
        )
        return report

    works, detail = _auth_probe(claude_path)
    report.results.append(
        CheckResult(
            label="Autenticación de Claude",
            ok=works,
            detail=f"{auth_status}. {detail}",
            remedy="La credencial existe pero no sirve — lo más común es que el "
            "token haya vencido. Abrí el acceso directo 'Iniciar sesión en "
            "Claude' para renovarla.",
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

    # Códigos distintos para fallas distintas: el instalador los usa para
    # dar la instrucción correcta. Un token vencido no se arregla
    # reconfigurando el .env, y mandar a reconfigurar cuando lo que hay
    # que hacer es iniciar sesión hace perder el tiempo y desconfiar del
    # reporte.
    auth_failed = any(
        not r.ok for r in report.results if r.label in ("Autenticación de Claude", "CLI de Claude")
    )
    other_failed = any(
        not r.ok
        for r in report.results
        if r.label not in ("Autenticación de Claude", "CLI de Claude")
    )
    # Se informan los dos por separado, y el caso "las dos cosas" tiene su
    # propio código: si sólo se reportara el problema de configuración, el
    # instalador no ofrecería renovar la credencial y haría falta una
    # segunda pasada para descubrir que también faltaba eso.
    if other_failed and auth_failed:
        return _EXIT_BOTH_PROBLEMS
    if other_failed:
        return _EXIT_CONFIG_PROBLEM
    if auth_failed:
        return _EXIT_AUTH_PROBLEM
    return 0


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

    from app import tray
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
        _splash("Verificando si SAVI ya está abierto...")
        if _savi_already_running(url):
            logger.info("SAVI ya estaba corriendo en %s; abriendo el navegador.", url)
            _splash(close=True)
            webbrowser.open(url)
            return

        # Lo tiene otra aplicación. Se busca otro puerto en vez de abortar:
        # abortar deja al usuario con la instrucción de editar un archivo
        # en Program Files, que necesita administrador y que no va a tocar.
        fallback = _resolve_port(browse_host, port + 1)
        if fallback is None:
            logger.error(
                "El puerto %s está ocupado y no hay ninguno libre en los %s siguientes.",
                port,
                _PORT_SCAN_RANGE,
            )
            _show_fatal_error(
                f"El puerto {port} está ocupado por otra aplicación, y tampoco "
                f"hay ninguno libre en los {_PORT_SCAN_RANGE} siguientes.\n\n"
                "Cerrá la aplicación que los está usando, o cambiá APP_PORT en "
                "el archivo .env."
            )
            raise SystemExit(1)

        logger.warning(
            "El puerto %s lo tiene otra aplicación; SAVI usa el %s en esta ejecución.",
            port,
            fallback,
        )
        port = fallback
        url = f"http://{browse_host}:{port}"

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

    # `Config` + `Server` en vez de `uvicorn.run()`: es lo mismo, pero deja
    # a mano el objeto que el icono de la bandeja necesita para poder
    # apagarlo cuando el usuario elige Salir.
    server = uvicorn.Server(
        uvicorn.Config(
            fastapi_app,
            host=host,
            port=port,
            log_config=None,
            # Sin esto, 'Salir' no cierra nada mientras haya un turno en
            # curso: uvicorn espera sin límite a que cierren las conexiones
            # abiertas, y el chat es un SSE que dura lo que dura la
            # respuesta. El usuario apretaría Salir, no pasaría nada, y
            # terminaría en el Administrador de tareas otra vez.
            timeout_graceful_shutdown=_SHUTDOWN_GRACE_S,
        )
    )
    tray.start(url, server)
    server.run()


if __name__ == "__main__":
    main()
