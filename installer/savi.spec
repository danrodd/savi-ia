# PyInstaller spec para el ejecutable de escritorio de SAVI.
#
# Modo `onedir` (no `onefile`) a propósito:
# - Arranque inmediato: `onefile` descomprime ~200 MB a un temporal en
#   cada ejecución.
# - Menos falsos positivos de antivirus, que desconfían de los binarios
#   auto-extraíbles.
# - El módulo `chat` lanza el binario `claude` como subproceso; con
#   `onefile` el directorio del bundle se borra al salir y complica el
#   ciclo de vida de ese subproceso.
#
# El "un solo .exe" que ve el usuario es el instalador de Inno Setup, que
# empaqueta este directorio completo.
#
# Uso: pyinstaller installer/savi.spec   (desde la raíz del monorepo)

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH lo inyecta PyInstaller
BACKEND = ROOT / "backend"

KNOWLEDGE_DATA = BACKEND / "app" / "modules" / "knowledge" / "data"
FRONTEND_BUILD = BACKEND / "frontend"


def _require(path: Path, explanation: str) -> Path:
    """Aborta el build si falta un recurso obligatorio.

    Sin esto el .exe se genera igual y falla recién en el equipo del
    cliente, que es el peor lugar posible para descubrirlo.
    """
    if not path.exists():
        raise SystemExit(f"\n[BUILD ABORTADO] Falta: {path}\n{explanation}\n")
    return path


_require(
    KNOWLEDGE_DATA,
    "Es el catalogo de conocimiento que SAVI carga al arrancar y sin el\n"
    "cual el backend no levanta (main.py -> init_catalog).\n"
    "Estructura esperada:\n"
    "  data/modules/<dossier>/overview.json\n"
    "  data/modules/<dossier>/{forms,workflows,faqs}/*.json\n"
    "  data/shared/glossary.json",
)

# El loader acepta un catalogo vacio (devuelve listas vacias), asi que la
# ausencia de contenido no rompe el build ni el arranque: SAVI levanta
# sin saber nada de la empresa. Se avisa fuerte para que no pase
# inadvertido en un release.
if not list(KNOWLEDGE_DATA.rglob("*.json")):
    print(
        "\n[ADVERTENCIA] El catalogo de conocimiento no tiene ningun .json:\n"
        f"  {KNOWLEDGE_DATA}\n"
        "  SAVI va a arrancar, pero sin conocimiento del ERP ni de la empresa.\n"
        "  Copia el catalogo real antes de distribuir este instalador.\n"
    )
_require(
    FRONTEND_BUILD,
    "Es el build de Vue que sirve el backend.\n"
    "Generalo con: installer/build.ps1  (o copiá frontend/dist a backend/frontend).",
)

datas = [
    # Alembic: el launcher corre las migraciones solo al arrancar.
    (str(BACKEND / "alembic"), "alembic"),
    (str(BACKEND / "alembic.ini"), "."),
    (str(KNOWLEDGE_DATA), "app/modules/knowledge/data"),
    (str(FRONTEND_BUILD), "frontend"),
]
# Plantillas .mako que alembic necesita para generar revisiones.
datas += collect_data_files("alembic")
# Base de datos de zonas horarias: Windows no trae una, y `zoneinfo` la
# necesita para agrupar el consumo por día local.
datas += collect_data_files("tzdata", include_py_files=False)

hiddenimports = [
    # uvicorn resuelve estos por string en runtime; el análisis estático
    # de PyInstaller no los ve.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    # Dialectos de SQLAlchemy: se cargan por nombre desde la URL.
    "aiosqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "sqlalchemy.dialects.postgresql.asyncpg",
    "asyncpg",
    # SDK y utilidades que se importan de forma indirecta.
    "claude_agent_sdk",
    "anthropic",
    "jwt",
    "tzdata",
]

# sqlglot resuelve los dialectos por nombre en runtime
# (`importlib.import_module("sqlglot.dialects.postgres")`), asi que el
# analisis estatico no ve ninguno y el bundle se arma sin ellos.
# Declarar solo "sqlglot" trae el paquete raiz y nada mas: el validador
# de SQL explotaba con ModuleNotFoundError en CADA consulta libre, ya
# instalado en el equipo del cliente y no aca.
hiddenimports += collect_submodules("sqlglot")

analysis = Analysis(  # noqa: F821
    [str(BACKEND / "app" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Pesan cientos de MB y no se usan en runtime.
    excludes=["tkinter", "pytest", "ruff", "pyright", "PIL", "numpy", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)  # noqa: F821

# Pantalla de arranque. La muestra el bootloader antes de que corra una
# sola linea de Python, que es justo el tramo en el que el usuario no
# tenia ninguna senal: entre el doble clic y el navegador pasan varios
# segundos (descompresion, imports, migracion) y la app no dibuja nada.
# El launcher le va escribiendo el paso actual con pyi_splash.update_text.
SPLASH_IMAGE = ROOT / "installer" / "assets" / "splash.png"
splash = Splash(  # noqa: F821
    str(SPLASH_IMAGE),
    binaries=analysis.binaries,
    datas=analysis.datas,
    text_pos=(24, 268),
    text_size=9,
    text_color="white",
    text_default="Iniciando SAVI...",
)

exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    splash,
    [],
    exclude_binaries=True,
    name="SAVI",
    debug=False,
    strip=False,
    upx=False,
    # Sin consola: una terminal parpadeando en cada apertura no es el look
    # de una app de escritorio. Los fallos de arranque van a savi.log y a
    # un MessageBox (launcher._show_fatal_error); `--check-config` se abre
    # su propia consola bajo demanda (launcher._ensure_console_for_diagnostics).
    console=False,
    icon=str(ROOT / "installer" / "assets" / "savi.ico")
    if (ROOT / "installer" / "assets" / "savi.ico").exists()
    else None,
)

COLLECT(  # noqa: F821
    exe,
    splash.binaries,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="SAVI",
)
