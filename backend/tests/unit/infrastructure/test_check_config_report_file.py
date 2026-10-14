"""`--check-config --report-file=...`: el modo que usa el instalador.

En un equipo de soporte la asociación de `.html` estaba rota: Windows mostraba
"¿Cómo quieres abrir este archivo?", se cerraba sola y el técnico no veía qué
había fallado. Con `--report-file` el reporte va a un archivo de texto que el
instalador muestra en su propia ventana, y no se abre el navegador.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.launcher as launcher
from app.diagnostics import CheckResult, Report


def _report() -> Report:
    report = Report(env_path="C:\\SAVI\\.env", generated_at="hoy", app_version="1.2.3")
    report.results.append(CheckResult("Base del ERP", ok=True, detail="Conexión correcta."))
    report.results.append(
        CheckResult(
            "La base de datos de SAVI",
            ok=False,
            detail="No se encontró el servidor 'srv'.",
            remedy="Revisá el nombre del servidor.",
        )
    )
    return report


def test_report_file_gets_the_text_and_the_browser_is_not_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(launcher, "_collect_report", _report)
    monkeypatch.setattr(launcher, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)
    target = tmp_path / "diagnostico-instalacion.txt"

    code = launcher._check_config(pause=False, report_file=target)  # pyright: ignore[reportPrivateUsage]

    text = target.read_text(encoding="mbcs")
    assert code != 0
    assert "[FALLA] La base de datos de SAVI" in text
    assert "-> Revisá el nombre del servidor." in text
    assert opened == []


def test_report_file_argument_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher.sys,
        "argv",
        ["SAVI.exe", "--check-config", '--report-file="C:\\ProgramData\\SAVI\\diag.txt"'],
    )

    assert launcher._report_file_arg() == Path("C:\\ProgramData\\SAVI\\diag.txt")  # pyright: ignore[reportPrivateUsage]
