"""Reporte de diagnóstico de la instalación, legible por una persona.

Lo lee un técnico en el equipo de un cliente, no un desarrollador: se
renderiza como una página HTML que se abre en el navegador en vez de
volcar texto en una consola que se cierra sola. Además queda como archivo,
así que se puede mandar por mail o adjuntar a un reporte de soporte.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CheckResult:
    """Un chequeo y su resultado, listo para renderizar."""

    label: str
    ok: bool
    detail: str
    # Qué hacer cuando falla. Es la diferencia entre un reporte que
    # informa y uno que desbloquea a quien lo está leyendo.
    remedy: str = ""


@dataclass
class Report:
    env_path: str
    generated_at: str
    app_version: str
    results: list[CheckResult] = field(default_factory=list["CheckResult"])

    @property
    def failures(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    def as_text(self) -> str:
        """Versión de consola, para el log y para el modo sin navegador."""
        lines = [f"SAVI {self.app_version}", f"Configuración leída de: {self.env_path}"]
        for r in self.results:
            mark = "[OK]   " if r.ok else "[FALLA]"
            lines.append(f"{mark} {r.label}: {r.detail}")
            if not r.ok and r.remedy:
                lines.append(f"         → {r.remedy}")
        lines.append(
            "\nSin problemas."
            if self.failures == 0
            else f"\n{self.failures} problema(s) encontrado(s)."
        )
        return "\n".join(lines)


_STYLES = """
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0; padding: 40px 20px;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  background: #f4f4f5; color: #18181b; line-height: 1.55;
}
.card {
  max-width: 720px; margin: 0 auto; background: #fff; border-radius: 14px;
  overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 8px 28px rgba(0,0,0,.06);
}
header { background: #bc0101; color: #fff; padding: 26px 32px; }
header h1 { margin: 0; font-size: 21px; letter-spacing: .01em; }
header p { margin: 4px 0 0; opacity: .85; font-size: 13px; }
.summary {
  padding: 18px 32px; font-weight: 600; font-size: 15px;
  border-bottom: 1px solid #e4e4e7;
}
.summary.ok   { background: #f0fdf4; color: #15803d; }
.summary.fail { background: #fef2f2; color: #b91c1c; }
ul { list-style: none; margin: 0; padding: 0; }
li { display: flex; gap: 14px; padding: 18px 32px; border-bottom: 1px solid #f4f4f5; }
li:last-child { border-bottom: 0; }
.mark {
  flex: 0 0 22px; height: 22px; border-radius: 50%; margin-top: 1px;
  display: grid; place-items: center; font-size: 13px; font-weight: 700; color: #fff;
}
.mark.ok   { background: #16a34a; }
.mark.fail { background: #dc2626; }
.label { font-weight: 600; }
.detail { color: #52525b; font-size: 14px; }
.detail code {
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 12.5px;
  background: #f4f4f5; padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere;
}
.remedy {
  margin-top: 8px; padding: 10px 13px; background: #fffbeb;
  border-left: 3px solid #f59e0b; border-radius: 0 6px 6px 0; font-size: 13.5px;
}
footer { padding: 16px 32px; background: #fafafa; color: #71717a; font-size: 12.5px; }
footer code { font-family: "Cascadia Mono", Consolas, monospace; overflow-wrap: anywhere; }
@media (prefers-color-scheme: dark) {
  body { background: #18181b; color: #f4f4f5; }
  .card { background: #232326; box-shadow: none; }
  li { border-bottom-color: #2e2e33; }
  .detail { color: #a1a1aa; }
  .detail code, footer code { background: #2e2e33; }
  .summary.ok   { background: #14261a; color: #4ade80; }
  .summary.fail { background: #2a1516; color: #f87171; }
  .remedy { background: #2a2415; }
  footer { background: #1d1d20; color: #a1a1aa; }
}
"""


def render_html(report: Report) -> str:
    rows: list[str] = []
    for r in report.results:
        state = "ok" if r.ok else "fail"
        remedy = (
            f'<div class="remedy">{html.escape(r.remedy)}</div>' if not r.ok and r.remedy else ""
        )
        rows.append(
            f'<li><span class="mark {state}">{"✓" if r.ok else "✕"}</span>'
            f'<div><div class="label">{html.escape(r.label)}</div>'
            f'<div class="detail">{html.escape(r.detail)}</div>{remedy}</div></li>'
        )

    if report.failures == 0:
        summary_class, summary = "ok", "Todo en orden. SAVI está listo para usarse."
    elif report.failures == 1:
        summary_class, summary = (
            "fail",
            "1 problema encontrado. SAVI no va a funcionar hasta corregirlo.",
        )
    else:
        summary_class, summary = (
            "fail",
            f"{report.failures} problemas encontrados. SAVI no va a funcionar hasta corregirlos.",
        )

    return (
        "<!doctype html>"
        '<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Diagnóstico de SAVI</title>"
        f"<style>{_STYLES}</style></head><body>"
        '<div class="card">'
        f"<header><h1>Diagnóstico de SAVI {html.escape(report.app_version)}</h1>"
        f"<p>{html.escape(report.generated_at)}</p></header>"
        f'<div class="summary {summary_class}">{html.escape(summary)}</div>'
        f"<ul>{''.join(rows)}</ul>"
        f"<footer>Configuración leída de <code>{html.escape(report.env_path)}</code></footer>"
        "</div></body></html>"
    )


def now_label() -> str:
    return datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
