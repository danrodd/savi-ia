"""Versión de SAVI — fuente única de todo el monorepo.

Sigue SemVer (https://semver.org/lang/es/): `MAJOR.MINOR.PATCH`.
`MAJOR` cuando algo rompe compatibilidad hacia atrás (ej. un endpoint
cambia de forma), `MINOR` para funcionalidad nueva compatible, `PATCH`
para arreglos.

Quién la usa:
- `pyproject.toml` — `[tool.hatch.version] path = "app/_version.py"`
  toma el número de acá. Es la única razón por la que el literal de
  abajo tiene que seguir siendo justamente eso: hatchling lo lee con
  una expresión regular, no ejecuta el archivo.
- En runtime: `GET /health`, el log de arranque y el reporte de
  diagnóstico del launcher (`--check-config` / "Diagnosticar SAVI")
  la exponen — es lo que dice qué build tiene instalado un cliente
  cuando llama a soporte.
- `installer/bump_version.py` la actualiza acá y replica el número a
  `frontend/package.json`; `installer/build.ps1` la lee de acá para
  pasarle `/DAppVersion=...` a Inno Setup. Este archivo es el ÚNICO
  lugar que hay que tocar a mano para lanzar una versión nueva — ver
  `installer/README.md#versionado`.
"""

__version__ = "0.1.0"
