# PyInstaller spec del chequeo de conexión que usa el asistente de
# instalación (`savi-dbcheck.exe`, ver backend/app/dbcheck.py).
#
# `onefile` a propósito, al revés que SAVI: el instalador lo extrae a un
# temporal y lo ejecuta antes de copiar nada, así que tiene que ser un
# solo archivo chico. No importa nada de la app: solo SQLAlchemy + asyncpg.
#
# Uso: pyinstaller installer/dbcheck.spec   (desde backend/, lo hace build.ps1)

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH lo inyecta PyInstaller
BACKEND = ROOT / "backend"

analysis = Analysis(  # noqa: F821
    [str(BACKEND / "app" / "dbcheck.py")],
    pathex=[],
    binaries=[],
    datas=[],
    # El dialecto se carga por nombre desde la URL y asyncpg trae módulos
    # nativos que el análisis estático no ve.
    hiddenimports=["sqlalchemy.dialects.postgresql.asyncpg", *collect_submodules("asyncpg")],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "numpy", "PIL", "onnxruntime", "fastembed", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="savi-dbcheck",
    debug=False,
    strip=False,
    upx=False,
    # Sin consola: el instalador lo corre oculto y lee el resultado de un archivo.
    console=False,
)
