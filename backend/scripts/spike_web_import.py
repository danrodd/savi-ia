"""Spike de la Fase 5: importar conocimiento desde la web.

Contexto: `docs/company_knowledge/05-fase-importar-desde-web.md` §12.
Resultado: `docs/company_knowledge/spike-web.md`.

No toca el módulo. Por cada URL:

- **S1** descarga simple (`httpx`) + `trafilatura` → Markdown;
- **S2** lo mismo con Chromium sin interfaz (imágenes, fuentes y media
  bloqueadas; espera a red quieta) y compara palabras para decidir el modo;
- **S3** tiempos de cada camino;
- **S4** memoria máxima del navegador y al cerrarlo.

Deja el Markdown de cada camino en `--out` para revisarlo a mano.

    uv run --with trafilatura --with playwright --with psutil \\
        python scripts/spike_web_import.py --out <carpeta> [URL ...]

Sin URLs usa la lista de §12 (sitios públicos de cada tipo) y el sitio de
prueba local si está levantado en `http://127.0.0.1:8765`.
"""

# ruff: noqa: E501

import argparse
import contextlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import psutil
import trafilatura
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

USER_AGENT = "SAVI-Knowledge/0.1 (+spike; contacto del administrador)"
BLOCKED_RESOURCES = {"image", "font", "media", "stylesheet"}
RENDER_TIMEOUT_MS = 15_000

PUBLIC_SITES = [
    ("wordpress", "https://wordpress.org/news/"),
    (
        "wordpress",
        "https://www.wpbeginner.com/beginners-guide/how-to-choose-the-best-blogging-platform/",
    ),
    ("nextjs", "https://nextjs.org/docs"),
    ("nextjs", "https://vercel.com/pricing"),
    ("nuxt", "https://nuxt.com/"),
    ("astro", "https://astro.build/"),
    ("astro", "https://docs.astro.build/en/getting-started/"),
    ("ssr-otro", "https://www.python.org/about/"),
]
LOCAL_SITE = [
    ("local-estatica", "http://127.0.0.1:8765/"),
    ("local-estatica", "http://127.0.0.1:8765/servicios.html"),
    ("local-pricing-js", "http://127.0.0.1:8765/planes.html"),
    ("local-spa", "http://127.0.0.1:8765/app.html"),
]


@dataclass
class Result:
    tipo: str
    url: str
    static_status: int | None = None
    static_ms: int = 0
    static_words: int = 0
    rendered_ms: int = 0
    rendered_words: int = 0
    decision: str = ""
    motivo: str = ""
    error: str = ""


def words(text: str | None) -> int:
    return len(re.findall(r"\w+", text or ""))


def extract(html: str, url: str) -> str:
    return (
        trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_tables=True,
            include_links=False,
            include_images=False,
            include_comments=False,
        )
        or ""
    )


def decide(static_words: int, rendered_words: int) -> tuple[str, str]:
    """Regla inicial del §4.3; el spike la calibra."""
    gained = rendered_words - static_words
    if static_words == 0 and rendered_words > 0:
        return "browser", "sin navegador no hay texto"
    if gained >= 300:
        return "browser", f"+{gained} palabras con navegador"
    if static_words and gained >= 20 and rendered_words >= static_words * 1.3:
        return "browser", f"+{gained} palabras ({rendered_words / static_words:.0%} del simple)"
    return "static", f"{gained:+} palabras con navegador"


class MemorySampler:
    """Suma el RSS de los procesos hijos (driver + Chromium) cada 100 ms."""

    def __init__(self) -> None:
        self.peak_mb = 0.0
        self._stop = threading.Event()
        self._me = psutil.Process()

    def current_mb(self) -> float:
        total = 0
        for child in self._me.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
        return total / 1024 / 1024

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak_mb = max(self.peak_mb, self.current_mb())
            time.sleep(0.1)

    def __enter__(self) -> "MemorySampler":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("urls", nargs="*")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    targets = [("manual", url) for url in args.urls] or PUBLIC_SITES + LOCAL_SITE
    results: list[Result] = []
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20)

    with MemorySampler() as memory, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, java_script_enabled=True)
        context.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in BLOCKED_RESOURCES
                else route.continue_()
            ),
        )
        for index, (kind, url) in enumerate(targets):
            result = Result(kind, url)
            slug = f"{index:02d}-{kind}"
            try:
                started = time.perf_counter()
                response = client.get(url)
                result.static_status = response.status_code
                static_md = extract(response.text, url)
                result.static_ms = int((time.perf_counter() - started) * 1000)
                result.static_words = words(static_md)
                (args.out / f"{slug}-simple.md").write_text(static_md, encoding="utf-8")

                page = context.new_page()
                started = time.perf_counter()
                page.goto(url, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS * 2)
                # Red que nunca se aquieta (analítica, websockets): seguimos igual.
                with contextlib.suppress(PlaywrightError):
                    page.wait_for_load_state("networkidle", timeout=RENDER_TIMEOUT_MS)
                for _ in range(3):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(300)
                rendered_md = extract(page.content(), url)
                page.close()
                result.rendered_ms = int((time.perf_counter() - started) * 1000)
                result.rendered_words = words(rendered_md)
                (args.out / f"{slug}-navegador.md").write_text(rendered_md, encoding="utf-8")
                result.decision, result.motivo = decide(result.static_words, result.rendered_words)
            except Exception as exc:  # noqa: BLE001 — es un spike: se registra y se sigue
                result.error = f"{type(exc).__name__}: {str(exc)[:160]}"
            results.append(result)
            print(
                f"{kind:16} {result.static_words:6} simple ({result.static_ms:5} ms) "
                f"{result.rendered_words:6} navegador ({result.rendered_ms:5} ms) "
                f"→ {result.decision or '-':7} {result.motivo or result.error}  {url}"
            )
        before_close = memory.current_mb()
        context.close()
        browser.close()

    after_close = MemorySampler().current_mb()
    summary = {
        "memoria_pico_mb": round(memory.peak_mb),
        "memoria_con_navegador_abierto_mb": round(before_close),
        "memoria_tras_cerrar_mb": round(after_close),
        "resultados": [asdict(r) for r in results],
    }
    (args.out / "resultado.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"\nMemoria del navegador: pico {summary['memoria_pico_mb']} MB, "
        f"abierto {summary['memoria_con_navegador_abierto_mb']} MB, "
        f"tras cerrar {summary['memoria_tras_cerrar_mb']} MB"
    )


if __name__ == "__main__":
    main()
