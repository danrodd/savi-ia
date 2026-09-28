"""Contenido principal de una página a Markdown (Fase 5).

Lo que se validó con sitios reales de clientes
(`docs/company_knowledge/prueba-sitios-clientes.md`):

- **Extracción híbrida.** Se corren dos extractores y se queda el que saca
  más texto. El estructural (`<main>` o el `body` sin la plantilla de la
  página, a Markdown con `markdownify`) conserva tarjetas de precios y
  listas cortas, que `trafilatura` descarta; `trafilatura` gana cuando el
  contenido no está en `<main>`.
- **`schema.org` en JSON-LD** (productos, empresa, sedes): en tiendas como
  VTEX el nombre y el precio del producto solo están ahí.
- **Precios partidos** en líneas (`$` / `31` / `.` / `00`) se unen.
- **Plantilla por repetición**: temas armados con `div` (Elementor) no usan
  `header`/`footer`; lo que se repite en la mitad de las páginas se quita
  de cada una y se guarda una vez.
"""

import json
import re
from typing import Any, cast

import trafilatura  # pyright: ignore[reportMissingTypeStubs]
from lxml import html as lxml_html  # pyright: ignore[reportMissingTypeStubs]
from markdownify import markdownify  # pyright: ignore[reportMissingTypeStubs]

from app.modules.company_knowledge.domain.entities.web_source import ExtractedPage
from app.modules.company_knowledge.domain.interfaces import ContentExtractor

_INSIDE = "ancestor::main or ancestor::article or ancestor::*[@role='main']"
_DROP = (
    "//script|//style|//noscript|//form|//iframe|//svg|//nav|//template|"
    f"//header[not({_INSIDE})]|//footer[not({_INSIDE})]|//aside[not({_INSIDE})]|"
    "//*[@role='navigation' or @role='banner' or @role='contentinfo' or @aria-hidden='true']|"
    "//*[contains(@class,'cookie') or contains(@id,'cookie')]"
)
_PRICE_SPLIT = re.compile(r"\$\s*\n\s*(\d[\d,]*)\s*\n\s*\.\s*\n\s*(\d{2})")
_PRICE_BREAK = re.compile(r"\$\s*\n\s*(\d)")
_JSON_LD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_HEADING = re.compile(r"^# +(.+)$", re.MULTILINE)
_BLANK_LINES = re.compile(r"\n{3,}")
_TRAFILATURA_MARGIN = 1.3
_FILLER = re.compile(r"lorem ipsum|dolor sit amet", re.IGNORECASE)
# El código solo ("MXN") no aparece en una búsqueda por "moneda" o "pesos".
_CURRENCIES = {
    "MXN": "pesos mexicanos",
    "COP": "pesos colombianos",
    "USD": "dólares estadounidenses",
    "EUR": "euros",
}
_BUSINESS_TYPES = frozenset({"Organization", "LocalBusiness", "Store", "Pharmacy", "Corporation"})


def count_words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def split_blocks(markdown: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", markdown) if block.strip()]


def _structural(html: str) -> str:
    # `lxml` no trae tipos completos: los nodos se manejan como `Any` solo
    # dentro de esta función.
    lxml: Any = cast(Any, lxml_html)
    parse: Any = lxml.fromstring
    to_string: Any = lxml.tostring
    try:
        tree: Any = parse(html)
    except (ValueError, TypeError):
        return ""
    element: Any
    for element in tree.xpath(_DROP):
        element.drop_tree()
    roots: Any = tree.xpath("//main") or tree.xpath("//*[@role='main']") or tree.xpath("//body")
    root: Any = roots[0] if roots else tree
    fragment = str(to_string(root, encoding="unicode"))
    to_markdown: Any = markdownify
    markdown = str(to_markdown(fragment, heading_style="ATX", strip=["a", "img"]))
    return _BLANK_LINES.sub("\n\n", markdown).strip()


_FOOTERS = f"//footer[not({_INSIDE})]|//*[@role='contentinfo']"
_FOOTER_NOISE = ".//script|.//style|.//noscript|.//form|.//iframe|.//svg|.//nav"


def _footer(html: str) -> str:
    """Texto del pie de la página, que `_structural` descarta con la plantilla."""
    lxml: Any = cast(Any, lxml_html)
    parse: Any = lxml.fromstring
    to_string: Any = lxml.tostring
    try:
        tree: Any = parse(html)
    except (ValueError, TypeError):
        return ""
    parts: list[str] = []
    element: Any
    for element in tree.xpath(_FOOTERS):
        noise: Any
        for noise in element.xpath(_FOOTER_NOISE):
            noise.drop_tree()
        to_markdown: Any = markdownify
        fragment = str(to_string(element, encoding="unicode"))
        text = str(to_markdown(fragment, heading_style="ATX", strip=["a", "img"])).strip()
        if text:
            parts.append(text)
    return _BLANK_LINES.sub("\n\n", "\n\n".join(parts)).strip()


def _trafilatura(html: str, url: str) -> str:
    extracted = trafilatura.extract(  # pyright: ignore[reportUnknownMemberType]
        html, url=url, output_format="markdown", include_tables=True
    )
    return extracted if isinstance(extracted, str) else ""


def _metadata_title(html: str, url: str) -> str:
    metadata = trafilatura.extract_metadata(html, default_url=url)  # pyright: ignore[reportUnknownMemberType]
    title = getattr(metadata, "title", None)
    return title.strip() if isinstance(title, str) else ""


def normalize(markdown: str) -> str:
    markdown = _PRICE_SPLIT.sub(r"$\1.\2", markdown)
    return _PRICE_BREAK.sub(r"$\1", markdown)


def _as_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _product_lines(item: dict[str, object]) -> list[str]:
    lines = [f"- Producto: {item.get('name', '')}"]
    offers = _as_dict(item.get("offers"))
    nested = offers.get("offers")
    offer = (
        _as_dict(cast(list[object], nested)[0]) if isinstance(nested, list) and nested else offers
    )
    if item.get("sku"):
        lines.append(f"- Código (SKU): {item['sku']}")
    brand = _as_dict(item.get("brand"))
    if brand.get("name"):
        lines.append(f"- Marca: {brand['name']}")
    price = offer.get("price") or offers.get("lowPrice")
    if price is not None:
        code = str(offer.get("priceCurrency") or offers.get("priceCurrency") or "")
        currency = f"{_CURRENCIES[code]} ({code})" if code in _CURRENCIES else code
        lines.append(f"- Precio: {price} {currency}".rstrip())
    availability = str(offer.get("availability", "")).rsplit("/", 1)[-1]
    if availability:
        label = "disponible" if availability == "InStock" else availability
        lines.append(f"- Disponibilidad: {label}")
    description = str(item.get("description") or "").strip()
    if len(description) > 3:
        lines.append(f"- Descripción: {description}")
    return lines


def _business_lines(item: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for key, label in (
        ("name", "Nombre"),
        ("telephone", "Teléfono"),
        ("email", "Correo"),
        ("openingHours", "Horario"),
    ):
        if item.get(key):
            lines.append(f"- {label}: {item[key]}")
    address = _as_dict(item.get("address"))
    parts = [
        str(address[k])
        for k in ("streetAddress", "addressLocality", "addressRegion")
        if address.get(k)
    ]
    if parts:
        lines.append(f"- Dirección: {', '.join(parts)}")
    return lines


def structured_data(html: str) -> str:
    """schema.org en JSON-LD como texto legible."""
    lines: list[str] = []
    for raw in _JSON_LD.findall(html):
        try:
            data: object = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            graph = _as_dict(cast(object, data)).get("@graph")
            items: list[object] = cast(list[object], graph) if isinstance(graph, list) else [data]
        elif isinstance(data, list):
            items = cast(list[object], data)
        else:
            continue
        for raw_item in items:
            item = _as_dict(raw_item)
            kind = item.get("@type")
            if kind == "Product":
                lines.extend(_product_lines(item))
            elif isinstance(kind, str) and kind in _BUSINESS_TYPES:
                lines.extend(_business_lines(item))
    return ("## Datos estructurados\n\n" + "\n".join(lines)) if lines else ""


def js_hints(html: str, markdown: str) -> tuple[str, ...]:
    hints: list[str] = []
    if re.search(r'<div id="(app|root|__next|__nuxt)"\s*>\s*</div>', html):
        hints.append("contenedor raíz vacío")
    if re.search(r"<noscript>[^<]*javascript", html, re.IGNORECASE):
        hints.append("pide JavaScript")
    if re.search(r"(cargando|loading)\s*(…|\.\.\.)", markdown, re.IGNORECASE):
        hints.append("texto 'cargando'")
    return tuple(hints)


class HybridContentExtractor(ContentExtractor):
    def extract(self, html: str, url: str) -> ExtractedPage:
        by_structure = _structural(html)
        by_trafilatura = _trafilatura(html, url)
        # La estructural descarta la plantilla por etiqueta: es la preferida.
        # `trafilatura` gana solo si saca BASTANTE más (contenido fuera de
        # `<main>`, como wordpress.org/news en el spike: 206 contra 110);
        # con una diferencia chica suele ser el menú que se le coló.
        words_structure = count_words(by_structure)
        prefer_trafilatura = count_words(by_trafilatura) > words_structure * _TRAFILATURA_MARGIN
        markdown = by_trafilatura if prefer_trafilatura else by_structure
        markdown = normalize(markdown)
        extra = structured_data(html)
        if extra:
            markdown = f"{markdown}\n\n{extra}" if markdown else extra
        # El primer título del contenido es más fiable que los metadatos: en
        # VTEX, `trafilatura` toma "Comentarios" como título del producto.
        heading = _HEADING.search(by_structure)
        title = heading.group(1).strip() if heading else _metadata_title(html, url)
        return ExtractedPage(
            title=title[:200],
            markdown=markdown,
            words=count_words(markdown),
            js_hints=js_hints(html, markdown),
            looks_like_filler=bool(_FILLER.search(markdown)),
            footer=normalize(_footer(html)),
        )

    def remove_boilerplate(
        self, pages: dict[str, str], share: float = 0.5
    ) -> tuple[dict[str, str], str]:
        blocks_by_url = {url: split_blocks(markdown) for url, markdown in pages.items()}
        # Con pocas páginas no hay forma de distinguir plantilla de contenido.
        if len(blocks_by_url) < 3:
            return dict(pages), ""
        counts: dict[str, int] = {}
        for blocks in blocks_by_url.values():
            for block in set(blocks):
                counts[block] = counts.get(block, 0) + 1
        threshold = max(3, int(len(blocks_by_url) * share))
        boilerplate = {block for block, count in counts.items() if count >= threshold}
        general: list[str] = []
        cleaned: dict[str, str] = {}
        for url, blocks in blocks_by_url.items():
            for block in blocks:
                if block in boilerplate and block not in general:
                    general.append(block)
            cleaned[url] = "\n\n".join(block for block in blocks if block not in boilerplate)
        return cleaned, "\n\n".join(general)
