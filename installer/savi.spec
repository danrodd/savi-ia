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

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
)

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH lo inyecta PyInstaller
BACKEND = ROOT / "backend"

KNOWLEDGE_DATA = BACKEND / "app" / "modules" / "knowledge" / "data"
FRONTEND_BUILD = BACKEND / "frontend"
# Caché de modelos de embeddings (la baja build.ps1).
EMBEDDING_MODELS = BACKEND / ".models"
# Modelo realmente usado. Debe coincidir con `company_docs_embedding_model`
# de `settings.py`: si cambia allá, cambiarlo acá.
EMBEDDING_MODEL_ID = "intfloat/multilingual-e5-small"


def _require(path: Path, explanation: str) -> Path:
    """Aborta el build si falta un recurso obligatorio.

    Sin esto el .exe se genera igual y falla recién en el equipo del
    cliente, que es el peor lugar posible para descubrirlo.
    """
    if not path.exists():
        raise SystemExit(f"\n[BUILD ABORTADO] Falta: {path}\n{explanation}\n")
    return path


def _embedding_model_datas():
    """Empaqueta SOLO el modelo de embeddings configurado.

    `.models` es la caché de HuggingFace de la máquina que buildea: junta
    todo lo que alguien haya probado alguna vez. Copiarla entera metía
    cinco modelos (2,5 GB) cuando SAVI usa uno, y el instalador terminaba
    pesando 1,8 GB en vez de ~400 MB.

    Si el modelo configurado cambia en `settings.py`, hay que cambiarlo
    acá también — y si no está descargado, el build aborta en vez de
    generar un .exe que falla en el equipo del cliente.
    """
    folder = "models--" + EMBEDDING_MODEL_ID.replace("/", "--")
    model_dir = _require(
        EMBEDDING_MODELS / folder,
        f"Es el modelo de embeddings '{EMBEDDING_MODEL_ID}' que usa el\n"
        "conocimiento de la empresa. Lo descarga build.ps1.",
    )
    datas = [(str(model_dir), f"models/{folder}")]
    # `CACHEDIR.TAG` marca la carpeta como caché de HuggingFace; va junto
    # al modelo para que la resolución desde el bundle no cambie.
    tag = EMBEDDING_MODELS / "CACHEDIR.TAG"
    if tag.exists():
        datas.append((str(tag), "models"))
    return datas


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

_require(
    EMBEDDING_MODELS,
    "Es el modelo de embeddings de los documentos de la empresa. SAVI no\n"
    "descarga nada en runtime: sin el, los documentos quedan en cola.\n"
    "Bajalo con: cd backend && uv run download-embedding-model",
)

datas = [
    # Alembic: el launcher corre las migraciones solo al arrancar.
    (str(BACKEND / "alembic"), "alembic"),
    (str(BACKEND / "alembic.ini"), "."),
    (str(KNOWLEDGE_DATA), "app/modules/knowledge/data"),
    (str(FRONTEND_BUILD), "frontend"),
    # `models_root()` lo busca en `<bundle>/models` cuando está congelado.
    # Solo el modelo EN USO, no la caché entera: `.models` es una caché de
    # HuggingFace y acumula todo lo que se haya probado alguna vez. Copiarla
    # completa metía 2 GB de modelos que SAVI no usa y cuadruplicaba el
    # instalador (1,8 GB contra ~400 MB).
    *_embedding_model_datas(),
]
# Plantillas .mako que alembic necesita para generar revisiones.
datas += collect_data_files("alembic")
# Base de datos de zonas horarias: Windows no trae una, y `zoneinfo` la
# necesita para agrupar el consumo por día local.
datas += collect_data_files("tzdata", include_py_files=False)

hiddenimports = [
    # La versión incrustada por build.ps1 (tag de git). Se importa dentro de
    # un try en app/_version.py: explícito para no depender del análisis
    # estático — sin ella, el .exe diría 0.0.0-dev.
    "app._build_version",
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
    "openai",
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

# Documentos de la empresa: fastembed descubre modelos y onnxruntime carga
# DLLs nativas en runtime; el analisis estatico no ve ninguna de las dos.
binaries: list[tuple[str, str]] = []
for package in ("fastembed", "onnxruntime", "tokenizers"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
hiddenimports += ["pypdf", "multipart", "python_multipart"]

analysis = Analysis(  # noqa: F821
    [str(BACKEND / "app" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Pesan cientos de MB y no se usan en runtime.
    # numpy y PIL NO se excluyen: los documentos de la empresa usan numpy, y
    # `fastembed` importa PIL al cargarse (`fastembed/common/types.py`) aunque
    # SAVI solo vectoriza texto. `main.py` importa ese modulo al arrancar:
    # excluirlos rompia el arranque del .exe entero, no solo los documentos.
    excludes=["tkinter", "pytest", "ruff", "pyright", "matplotlib"],
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
