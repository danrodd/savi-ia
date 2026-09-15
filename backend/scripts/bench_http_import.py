# ruff: noqa: E501 — script de medición con tablas markdown largas.
"""Importación de punta a punta contra SAVI corriendo (HTTP + Postgres + worker).

Uso (con `uv run dev` levantado y un administrador del ERP):

    uv run python -m scripts.bench_http_import --login admin --password 123
    uv run python -m scripts.bench_http_import --keep     # deja los documentos cargados

Sube los documentos del set de evaluación y PDF densos generados, y mide lo
que vive el usuario:

- subida: cuánto tarda el POST (lectura, validación y guardado del archivo);
- espera: desde que termina la subida hasta que el documento queda `ready`
  (incluye la cola: los documentos se procesan de a uno);
- búsqueda mientras se procesa: latencia de `search-test` con un PDF grande
  en proceso (RNF-02: el resto de SAVI no se tiene que trabar).

Escribe `docs/company_knowledge/bench-http-importacion.md`. Al terminar
borra los documentos que subió, salvo `--keep`.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from scripts.bench_company_ingest import _page_text, _sentences
from scripts.build_eval_pdfs import build_pdf

ROOT = Path(__file__).resolve().parents[1]
EVAL_DOCS = ROOT / "tests" / "fixtures" / "company_knowledge" / "eval" / "documents"
REPORT = ROOT / "docs" / "company_knowledge" / "bench-http-importacion.md"
MEDIA_TYPES = {".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain"}
TERMINAL = {"ready", "failed", "no_text"}


@dataclass
class Upload:
    name: str
    size: int
    pages: int | None = None
    document_id: str = ""
    upload_s: float = 0.0
    uploaded_at: float = 0.0
    ready_at: float = 0.0
    status: str = ""
    chunks: int | None = None
    search_ms: list[float] = field(default_factory=list[float])


def _files(pdf_pages: list[int]) -> list[tuple[str, bytes]]:
    files = [(p.name, p.read_bytes()) for p in sorted(EVAL_DOCS.iterdir())]
    rng = random.Random(11)
    sentences = _sentences()
    for pages in pdf_pages:
        body = [_page_text(rng, sentences, i + 1) for i in range(pages)]
        # Semilla distinta en cada corrida: el backend rechaza duplicados por contenido.
        body[0] += f"\n\nCorrida {time.time_ns()}"
        files.append((f"bench-denso-{pages}-paginas.pdf", build_pdf(body)))
    return files


async def _login(client: httpx.AsyncClient, login: str, password: str) -> None:
    response = await client.post("/auth/login", json={"login": login, "password": password})
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


async def _database_id(client: httpx.AsyncClient) -> str:
    response = await client.get("/admin/erp-databases")
    response.raise_for_status()
    active = [db for db in response.json() if db.get("is_active")]
    return active[0]["id"]


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--login", default="admin")
    parser.add_argument("--password", default="123")
    parser.add_argument("--pdf-pages", nargs="+", type=int, default=[50, 200])
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=120) as client:
        await _login(client, args.login, args.password)
        database_id = await _database_id(client)
        uploads: list[Upload] = []
        started = time.perf_counter()
        for name, content in _files(args.pdf_pages):
            item = Upload(name=name, size=len(content))
            t0 = time.perf_counter()
            response = await client.post(
                "/admin/company-documents",
                files={"file": (name, content, MEDIA_TYPES[Path(name).suffix])},
                data={"visibility": "all", "title": Path(name).stem},
            )
            item.upload_s = time.perf_counter() - t0
            item.uploaded_at = time.perf_counter()
            if response.status_code != 201:
                item.status = f"rechazado {response.status_code}: {response.text[:120]}"
                uploads.append(item)
                continue
            item.document_id = response.json()["id"]
            uploads.append(item)
            print(
                f"subido {name} ({len(content) / 1024:.0f} KB) en {item.upload_s * 1000:.0f} ms",
                flush=True,
            )

        pending = {u.document_id: u for u in uploads if u.document_id}
        largest = max((u for u in uploads if u.document_id), key=lambda u: u.size)
        while pending:
            listing = (await client.get("/admin/company-documents")).json()
            by_id = {d["id"]: d for d in listing}
            now = time.perf_counter()
            for document_id, item in list(pending.items()):
                doc = by_id.get(document_id)
                if doc is None:
                    continue
                if doc["status"] == "processing" and item is largest:
                    t0 = time.perf_counter()
                    await client.post(
                        "/admin/company-documents/search-test",
                        json={
                            "query": "¿Cuántos días de vacaciones tengo?",
                            "erp_database_id": database_id,
                        },
                    )
                    item.search_ms.append((time.perf_counter() - t0) * 1000)
                if doc["status"] in TERMINAL:
                    item.status = doc["status"]
                    item.pages = doc.get("page_count")
                    item.chunks = doc.get("chunk_count")
                    item.ready_at = now
                    del pending[document_id]
                    print(
                        f"{item.name}: {item.status} a los {item.ready_at - item.uploaded_at:.1f} s de subido",
                        flush=True,
                    )
            await asyncio.sleep(0.5)
        total = time.perf_counter() - started

        idle_ms: list[float] = []
        for _ in range(10):
            t0 = time.perf_counter()
            await client.post(
                "/admin/company-documents/search-test",
                json={
                    "query": "¿Cuántos días de vacaciones tengo?",
                    "erp_database_id": database_id,
                },
            )
            idle_ms.append((time.perf_counter() - t0) * 1000)

        if not args.keep:
            for item in uploads:
                if item.document_id:
                    await client.delete(f"/admin/company-documents/{item.document_id}")

    lines = [
        "# Importación de punta a punta — resultados",
        "",
        "> Generado por `scripts/bench_http_import.py` contra SAVI corriendo (HTTP, Postgres, worker real).",
        "> Los documentos se procesan de a uno: la espera incluye la cola.",
        "",
        "| Documento | Tamaño | Páginas | Subida | Espera hasta listo | Estado |",
        "|---|---|---|---|---|---|",
    ]
    for item in uploads:
        wait = f"{item.ready_at - item.uploaded_at:.1f} s" if item.ready_at else "—"
        lines.append(
            f"| {item.name} | {item.size / 1024:.0f} KB | {item.pages or '—'} | {item.upload_s * 1000:.0f} ms | {wait} | {item.status} |"
        )
    busy = largest.search_ms
    lines += [
        "",
        f"Total del lote: **{total:.1f} s**.",
        "",
        "## Búsqueda mientras se procesa (RNF-02)",
        "",
        "| Situación | Muestras | Mediana | Máximo |",
        "|---|---|---|---|",
        f"| Sin procesamiento | {len(idle_ms)} | {statistics.median(idle_ms):.0f} ms | {max(idle_ms):.0f} ms |",
    ]
    if busy:
        lines.append(
            f"| Procesando {largest.name} | {len(busy)} | {statistics.median(busy):.0f} ms | {max(busy):.0f} ms |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(_main())
