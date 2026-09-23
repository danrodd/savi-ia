"""Prueba con sitios reales de clientes, antes de construir la Fase 5.

Contexto: `docs/company_knowledge/05-fase-importar-desde-web.md` (orden
acordado) y `spike-web.md`. Resultado: `docs/company_knowledge/prueba-sitios-clientes.md`.

Solo descarga simple (sin navegador) y el pipeline de documentos actual:

1. ``extraer``: descubre páginas (sitemap o links), las descarga con pausa,
   extrae el contenido principal (híbrido: estructural + `trafilatura`),
   agrega los datos de `schema.org`, quita la plantilla repetida del sitio
   y deja un Markdown por página más `manifiesto.json` en ``--out``.
2. ``subir``: sube ese Markdown como documentos al backend (prefijo
   ``[QA web]``), con el alcance por base de cada sitio.

Las preguntas se hacen con ``bateria_web_clientes.py`` una vez revisado lo
extraído.

    uv run --with trafilatura --with markdownify python scripts/prueba_sitios_clientes.py extraer
    uv run python scripts/prueba_sitios_clientes.py subir
"""

# ruff: noqa: E501

import argparse
import json
import re
import tempfile
import time
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

OUT = Path(tempfile.gettempdir()) / "savi-sitios-clientes"
USER_AGENT = "SAVI-Knowledge/0.1 (prueba de importacion de conocimiento)"
PREFIX = "[QA web] "
DELAY_S = 1.0
MIN_WORDS = 25
# Un bloque que aparece en al menos esta fracción de las páginas es plantilla.
BOILERPLATE_SHARE = 0.5

# Rutas que no aportan conocimiento: cuenta, carrito, pagos, búsquedas. El
# sufijo `-2` cubre las copias que dejan algunos temas de WordPress.
EXCLUDED = re.compile(
    r"/(cart|carrito|checkout|my-account|mi-cuenta|account|login|registro|busca|search|"
    r"wishlist|order-tracking|wp-admin|wp-login|feed|tag|author|quick-view|step)"
    r"(-\d+)?(/|$)|[?&](add-to-cart|orderby|s)=",
    re.IGNORECASE,
)


@dataclass
class Site:
    code: str
    name: str
    root: str
    base: str | None  # código de la base del ERP; None = todas
    max_pages: int
    # Cupo por grupo del sitemap (prefijo del archivo) y grupos excluidos:
    # es lo que el administrador elegiría en la vista previa.
    quotas: dict[str, int] = field(default_factory=dict[str, int])
    exclude: list[str] = field(default_factory=list[str])


SITES = [
    # Las entradas y categorías del blog son la demo del tema (bicicletas).
    Site(
        "seo",
        "SEO Group (seo-erp.com)",
        "https://www.seo-erp.com/",
        None,
        60,
        exclude=[
            "wp-sitemap-posts-post",
            "wp-sitemap-taxonomies-category",
            "wp-sitemap-posts-cartflows",
        ],
    ),
    Site("surandina", "Sur Andina", "https://www.surandina.com.co/", "SUR_ANDINA", 60),
    Site(
        "farmacias",
        "Farmacias de Similares",
        "https://www.farmaciasdesimilares.com/",
        "FARMACIAS_SIMILARES",
        80,
        quotas={"custom-user-routes": 10, "category": 30, "product": 40},
        exclude=["brand"],
    ),
]


@dataclass
class Page:
    site: str
    url: str
    status: int = 0
    title: str = ""
    words_structural: int = 0
    words_trafilatura: int = 0
    words: int = 0
    extractor: str = ""
    file: str = ""
    skipped: str = ""
    js_hints: list[str] = field(default_factory=list[str])


# ── Extracción híbrida (spike §2) ────────────────────────────────────────

_INSIDE = "ancestor::main or ancestor::article or ancestor::*[@role='main']"
_DROP = (
    "//script|//style|//noscript|//form|//iframe|//svg|//nav|"
    f"//header[not({_INSIDE})]|//footer[not({_INSIDE})]|//aside[not({_INSIDE})]|"
    "//*[@role='navigation' or @role='banner' or @role='contentinfo' or @aria-hidden='true']|"
    "//*[contains(@class,'cookie') or contains(@id,'cookie')]"
)
_PRICE_SPLIT = re.compile(r"\$\s*\n\s*(\d[\d,]*)\s*\n\s*\.\s*\n\s*(\d{2})")
_PRICE_BREAK = re.compile(r"\$\s*\n\s*(\d)")
_JSON_LD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S)


def count_words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def structural(html: str) -> str:
    from lxml import html as lxml_html
    from markdownify import markdownify

    tree = lxml_html.fromstring(html)
    for element in tree.xpath(_DROP):
        element.drop_tree()
    roots = tree.xpath("//main") or tree.xpath("//*[@role='main']") or tree.xpath("//body")
    root = roots[0] if roots else tree
    markdown = markdownify(
        lxml_html.tostring(root, encoding="unicode"), heading_style="ATX", strip=["a", "img"]
    )
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


def extract(html: str, url: str) -> tuple[str, str, int, int, str]:
    import trafilatura

    by_structure = structural(html)
    by_trafilatura = (
        trafilatura.extract(html, url=url, output_format="markdown", include_tables=True) or ""
    )
    # El primer título del contenido es más fiable que los metadatos: en
    # VTEX, `trafilatura` toma "Comentarios" como título del producto.
    heading = re.search(r"^# +(.+)$", by_structure, re.MULTILINE)
    metadata = trafilatura.extract_metadata(html, default_url=url)
    title = (
        heading.group(1) if heading else (metadata.title if metadata and metadata.title else "")
    ).strip()
    a, b = count_words(by_structure), count_words(by_trafilatura)
    if a >= b:
        return by_structure, "estructural", a, b, title
    return by_trafilatura, "trafilatura", a, b, title


def normalize(markdown: str) -> str:
    """Une precios partidos en líneas ("$", "31", ".", "00" → "$31.00")."""
    markdown = _PRICE_SPLIT.sub(r"$\1.\2", markdown)
    return _PRICE_BREAK.sub(r"$\1", markdown)


# El código solo ("MXN") no aparece en una búsqueda por "moneda" o "pesos".
_CURRENCIES = {
    "MXN": "pesos mexicanos",
    "COP": "pesos colombianos",
    "USD": "dólares estadounidenses",
}


def _product_lines(item: dict[str, object]) -> list[str]:
    lines = [f"- Producto: {item.get('name', '')}"]
    offers = item.get("offers")
    offer: dict[str, object] = {}
    if isinstance(offers, dict):
        nested = offers.get("offers")
        offer = nested[0] if isinstance(nested, list) and nested else offers
    if item.get("sku"):
        lines.append(f"- Código (SKU): {item['sku']}")
    brand = item.get("brand")
    if isinstance(brand, dict) and brand.get("name"):
        lines.append(f"- Marca: {brand['name']}")
    price = offer.get("price") or (offers.get("lowPrice") if isinstance(offers, dict) else None)
    if price is not None:
        code = str(offer.get("priceCurrency") or "")
        currency = f"{_CURRENCIES[code]} ({code})" if code in _CURRENCIES else code
        lines.append(f"- Precio: {price} {currency}".rstrip())
    availability = str(offer.get("availability", "")).rsplit("/", 1)[-1]
    if availability:
        lines.append(
            f"- Disponibilidad: {'disponible' if availability == 'InStock' else availability}"
        )
    description = str(item.get("description") or "").strip()
    if len(description) > 3:
        lines.append(f"- Descripción: {description}")
    return lines


def structured_data(html: str) -> str:
    """schema.org en JSON-LD (productos, empresa, sedes) como texto."""
    lines: list[str] = []
    for raw in _JSON_LD.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data.get("@graph", [data]) if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get("@type")
            if kind == "Product":
                lines.extend(_product_lines(item))
            elif kind in ("Organization", "LocalBusiness", "Store", "Pharmacy"):
                for key, label in (
                    ("name", "Nombre"),
                    ("telephone", "Teléfono"),
                    ("email", "Correo"),
                    ("openingHours", "Horario"),
                ):
                    if item.get(key):
                        lines.append(f"- {label}: {item[key]}")
    return ("## Datos estructurados\n\n" + "\n".join(lines)) if lines else ""


def js_hints(html: str, markdown: str) -> list[str]:
    """Indicios de contenido que solo aparece con navegador."""
    hints = []
    if re.search(r'<div id="(app|root|__next)"\s*>\s*</div>', html):
        hints.append("contenedor raíz vacío")
    if re.search(r"<noscript>[^<]*(javascript|JavaScript)", html):
        hints.append("noscript pide JavaScript")
    if re.search(r"(cargando|loading)\s*(…|\.\.\.)", markdown, re.IGNORECASE):
        hints.append("texto 'cargando'")
    return hints


def split_blocks(markdown: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]


# ── Descubrimiento ───────────────────────────────────────────────────────


def sitemap_urls(client: httpx.Client, url: str, depth: int = 0) -> list[tuple[str, str]]:
    """(url, nombre del sitemap de origen); sigue índices de sitemaps."""
    try:
        text = client.get(url).text
    except httpx.HTTPError:
        return []
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", text)
    if "<sitemapindex" in text and depth < 2:
        found: list[tuple[str, str]] = []
        for child in locs:
            found.extend(sitemap_urls(client, child, depth + 1))
        return found
    return [(loc, url.rsplit("/", 1)[-1]) for loc in locs]


def crawl_links(client: httpx.Client, root: str, limit: int, depth: int = 2) -> list[str]:
    host = urlparse(root).netloc
    seen, frontier, found = {root}, [root], [root]
    for _ in range(depth):
        following = []
        for url in frontier:
            try:
                html = client.get(url).text
            except httpx.HTTPError:
                continue
            time.sleep(DELAY_S)
            for href in re.findall(r'href=["\']([^"\'#]+)', html):
                target = urldefrag(urljoin(url, href))[0]
                if urlparse(target).netloc != host or target in seen:
                    continue
                seen.add(target)
                following.append(target)
                found.append(target)
                if len(found) >= limit:
                    return found
        frontier = following
    return found


def discover(
    client: httpx.Client, site: Site, robots: urllib.robotparser.RobotFileParser
) -> list[str]:
    entries = sitemap_urls(client, urljoin(site.root, "sitemap.xml")) or sitemap_urls(
        client, urljoin(site.root, "wp-sitemap.xml")
    )
    if entries:
        used: dict[str, int] = {}
        urls = [site.root]
        for url, origin in entries:
            if any(origin.startswith(prefix) for prefix in site.exclude):
                continue
            group = next((prefix for prefix in site.quotas if origin.startswith(prefix)), None)
            if group is not None:
                if used.get(group, 0) >= site.quotas[group]:
                    continue
                used[group] = used.get(group, 0) + 1
            urls.append(url)
    else:
        urls = crawl_links(client, site.root, site.max_pages * 2)
    selected: list[str] = []
    for url in urls:
        if url in selected or EXCLUDED.search(url) or not robots.can_fetch(USER_AGENT, url):
            continue
        selected.append(url)
        if len(selected) >= site.max_pages:
            break
    return selected


# ── Etapas ───────────────────────────────────────────────────────────────


def _remove_boilerplate(
    out: Path, site: Site, texts: dict[str, tuple[Page, list[str]]]
) -> list[Page]:
    """Quita los bloques repetidos en muchas páginas y los guarda una vez.

    El menú, el pie con teléfonos y el carrito de un tema hecho con divs
    (Elementor) no se reconocen por etiqueta: se reconocen porque se repiten.
    Lo útil de esos bloques (teléfonos, dirección) queda en un documento
    "Información general del sitio".
    """
    if not texts:
        return []
    counts: dict[str, int] = {}
    for _page, blocks in texts.values():
        for block in set(blocks):
            counts[block] = counts.get(block, 0) + 1
    threshold = max(3, int(len(texts) * BOILERPLATE_SHARE))
    boilerplate = {block for block, count in counts.items() if count >= threshold}
    general: list[str] = []
    for url, (page, blocks) in texts.items():
        for block in blocks:
            if block in boilerplate and block not in general:
                general.append(block)
        kept = [block for block in blocks if block not in boilerplate]
        page.words = count_words("\n".join(kept))
        if page.words < MIN_WORDS:
            page.skipped, page.file = "solo plantilla", ""
            continue
        header = f"# {page.title or url}\n\nFuente: {url}\n\n"
        (out / page.file).write_text(header + "\n\n".join(kept), encoding="utf-8")
    print(f"   plantilla: {len(boilerplate)} bloques repetidos en ≥{threshold} páginas")
    if not general:
        return []
    name = f"{site.code}-general.md"
    (out / name).write_text(
        f"# {site.name}: información general del sitio\n\nFuente: {site.root}\n\n"
        + "\n\n".join(general),
        encoding="utf-8",
    )
    return [
        Page(
            site.code,
            site.root,
            200,
            "Información general del sitio",
            words=count_words("\n".join(general)),
            extractor="plantilla",
            file=name,
        )
    ]


def _read_page(
    client: httpx.Client, out: Path, site: Site, index: int, url: str, seen: set[int]
) -> tuple[Page, list[str] | None]:
    page = Page(site.code, url)
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        page.skipped = f"error {type(exc).__name__}"
        return page, None
    page.status = response.status_code
    content_type = response.headers.get("content-type", "")
    if response.status_code >= 400:
        page.skipped = f"HTTP {response.status_code}"
        return page, None
    if "pdf" in content_type:
        page.file = f"{site.code}-{index:03d}.pdf"
        (out / page.file).write_bytes(response.content)
        page.extractor, page.title = "pdf", url.rsplit("/", 1)[-1]
        return page, None
    if "html" not in content_type:
        page.skipped = f"tipo {content_type.split(';')[0]}"
        return page, None
    markdown, how, a, b, title = extract(response.text, url)
    markdown = normalize(markdown)
    extra = structured_data(response.text)
    if extra:
        markdown = f"{markdown}\n\n{extra}"
    page.words_structural, page.words_trafilatura = a, b
    page.words, page.extractor, page.title = count_words(markdown), how, title
    page.js_hints = js_hints(response.text, markdown)
    digest = hash(markdown)
    if page.words < MIN_WORDS:
        page.skipped = "sin texto útil"
        return page, None
    if digest in seen:
        page.skipped = "duplicada"
        return page, None
    seen.add(digest)
    page.file = f"{site.code}-{index:03d}.md"
    return page, split_blocks(markdown)


def cmd_extract(out: Path, only: list[str] | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
    pages: list[Page] = []
    for site in SITES:
        if only and site.code not in only:
            continue
        robots = urllib.robotparser.RobotFileParser(urljoin(site.root, "robots.txt"))
        try:
            robots.read()
        except OSError:
            robots.parse([])
        urls = discover(client, site, robots)
        print(f"\n== {site.name}: {len(urls)} páginas a leer")
        seen: set[int] = set()
        texts: dict[str, tuple[Page, list[str]]] = {}
        for index, url in enumerate(urls):
            page, blocks = _read_page(client, out, site, index, url, seen)
            if blocks is not None:
                texts[url] = (page, blocks)
            pages.append(page)
            time.sleep(DELAY_S)
        pages.extend(_remove_boilerplate(out, site, texts))
        for page in (p for p in pages if p.site == site.code):
            flag = "  " if page.file else "--"
            hints = f"⚠ {', '.join(page.js_hints)} " if page.js_hints else ""
            print(
                f"{flag} {page.words:5} ({page.extractor or '-':11}) {page.skipped} {hints}{page.url}"
            )
    (out / "manifiesto.json").write_text(
        json.dumps([asdict(p) for p in pages], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for site in SITES:
        rows = [p for p in pages if p.site == site.code]
        if rows:
            kept = [p for p in rows if p.file]
            print(
                f"\n{site.name}: {len(kept)}/{len(rows)} documentos, "
                f"{sum(p.words for p in kept)} palabras, "
                f"estructural gana en {sum(p.extractor == 'estructural' for p in kept)}, "
                f"indicios de JS en {sum(bool(p.js_hints) for p in rows)}"
            )


def cmd_upload(out: Path, api: str) -> None:
    pages = [Page(**p) for p in json.loads((out / "manifiesto.json").read_text(encoding="utf-8"))]
    client = httpx.Client(base_url=api, timeout=120)
    token = client.post("/auth/login", json={"login": "SAVIQA", "password": "123"}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    bases = {
        b["code"]: b["id"] for b in client.get("/erp-databases/available", headers=headers).json()
    }
    listing = client.get("/admin/company-documents", headers=headers, params={"limit": 200})
    for doc in listing.json():
        if doc["title"].startswith(PREFIX):
            client.delete(f"/admin/company-documents/{doc['id']}", headers=headers)
    by_code = {site.code: site for site in SITES}
    uploaded = 0
    for page in pages:
        if not page.file:
            continue
        site = by_code[page.site]
        form: dict[str, str | list[str]] = {
            "title": (PREFIX + f"{site.name} · {page.title or page.url}")[:200],
            "visibility": "all",
            "all_databases": "false" if site.base else "true",
        }
        if site.base:
            form["database_ids"] = [bases[site.base]]
        media = "application/pdf" if page.file.endswith(".pdf") else "text/markdown"
        while True:
            response = client.post(
                "/admin/company-documents",
                headers=headers,
                files={"file": (page.file, (out / page.file).read_bytes(), media)},
                data=form,
            )
            # Límite de subidas por usuario: el módulo web real crea los
            # documentos por dentro y no pasa por él.
            if response.status_code != 429:
                break
            wait = int(response.headers.get("retry-after", "20"))
            print(f"   límite de subidas, espero {wait} s…")
            time.sleep(wait)
        if response.status_code == 409:
            print(f"   duplicado, se omite: {page.url}")
            continue
        response.raise_for_status()
        uploaded += 1
    print(f"Subidos {uploaded} documentos. Esperando a que se procesen…")
    started = time.time()
    while time.time() - started < 900:
        docs = [
            d
            for d in client.get(
                "/admin/company-documents", headers=headers, params={"limit": 200}
            ).json()
            if d["title"].startswith(PREFIX)
        ]
        if not [d for d in docs if d["status"] in ("pending", "processing")]:
            summary: dict[str, int] = {}
            for d in docs:
                summary[d["status"]] = summary.get(d["status"], 0) + 1
            print(f"Listo: {summary}")
            return
        time.sleep(5)
    raise SystemExit("Los documentos no terminaron de procesarse")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("etapa", choices=["extraer", "subir"])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--solo", nargs="*", help="códigos de sitio (seo, surandina, farmacias)")
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    if args.etapa == "extraer":
        cmd_extract(args.out, args.solo)
    else:
        cmd_upload(args.out, args.api)


if __name__ == "__main__":
    main()
