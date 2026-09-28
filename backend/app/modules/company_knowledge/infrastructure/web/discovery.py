"""Descubre las páginas de un sitio: sitemap o, si no hay, siguiendo links.

- **Sitemap**: el que indica `robots.txt` o los nombres habituales
  (`/sitemap.xml`, `/sitemap_index.xml`, `/wp-sitemap.xml`). Sigue índices
  de sitemaps y lee `.gz` con tope de tamaño descomprimido. Cada sitemap
  hijo es una **sección** ("entradas", "páginas", "productos"): la vista
  previa las muestra para que el administrador excluya, por ejemplo, las
  entradas de demostración del tema.
- **Links**: recorrido en anchura desde la raíz, mismo sitio, con tope de
  profundidad y de páginas.

Todo pasa por el `WebFetcher`, que aplica la guarda contra SSRF.
"""

import asyncio
import gzip
import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeElementTree  # pyright: ignore[reportMissingTypeStubs]

from app.modules.company_knowledge.domain.entities.web_source import (
    DiscoveredUrl,
    Discovery,
)
from app.modules.company_knowledge.domain.exceptions import UnsafeUrlError, WebFetchError
from app.modules.company_knowledge.domain.interfaces import PageDiscoverer, WebFetcher

LINKS_SECTION = "links"
_SITEMAP_NAMES = ("sitemap.xml", "sitemap_index.xml", "wp-sitemap.xml")
_MAX_CHILD_SITEMAPS = 50
_MAX_SITEMAP_BYTES = 20 * 1024 * 1024
_TRACKING = re.compile(r"^(utm_\w+|gclid|fbclid|msclkid|mc_cid|mc_eid|_ga)$", re.IGNORECASE)
# Rutas que no aportan conocimiento: cuenta, carrito, pagos, búsquedas. El
# sufijo `-2` cubre las copias que dejan algunos temas de WordPress.
_EXCLUDED_PATH = re.compile(
    r"/(cart|carrito|checkout|my-account|mi-cuenta|account|login|logout|registro|register|"
    r"busca|buscar|search|wishlist|order-tracking|wp-admin|wp-login|wp-json|feed|tag|author|"
    r"quick-view|step)(-\d+)?(/|$)",
    re.IGNORECASE,
)
_EXCLUDED_QUERY = frozenset({"add-to-cart", "orderby", "s", "replytocom"})
# Recursos que no son páginas. PDF sí: catálogos y fichas se importan.
_NOT_PAGES = re.compile(
    r"\.(css|js|json|xml|txt|ico|png|jpe?g|gif|webp|svg|avif|bmp|mp[34]|webm|mov|avi|"
    r"zip|rar|7z|gz|exe|msi|dmg|woff2?|ttf|eot|docx?|xlsx?|pptx?)$",
    re.IGNORECASE,
)
_HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.IGNORECASE)


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def normalize_url(url: str) -> str:
    """Sin fragmento ni parámetros de seguimiento; esquema y host en minúscula."""
    clean, _ = urldefrag(url.strip())
    parts = urlsplit(clean)
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _TRACKING.match(k)
        ]
    )
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def is_excluded(url: str) -> bool:
    parts = urlsplit(url)
    if _EXCLUDED_PATH.search(parts.path) or _NOT_PAGES.search(parts.path):
        return True
    return any(key in _EXCLUDED_QUERY for key, _ in parse_qsl(parts.query))


def _children(root: Element, tag: str) -> list[str]:
    values: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == tag:
            for child in element:
                if child.tag.rsplit("}", 1)[-1] == "loc" and child.text:
                    values.append(child.text.strip())
    return values


class SitemapAndLinksDiscoverer(PageDiscoverer):
    def __init__(self, fetcher: WebFetcher, *, max_depth: int, request_delay_s: float) -> None:
        self._fetcher = fetcher
        self._max_depth = max_depth
        self._delay_s = request_delay_s

    async def discover(
        self, root: str, *, max_pages: int, excluded_sections: Sequence[str]
    ) -> Discovery:
        root = normalize_url(root)
        entries = await self._from_sitemaps(root)
        used_sitemap = bool(entries)
        if not entries:
            entries = [(url, LINKS_SECTION) for url in await self._from_links(root, max_pages * 2)]
        sections: dict[str, int] = {}
        for _url, section in entries:
            sections[section] = sections.get(section, 0) + 1

        selected: list[DiscoveredUrl] = [DiscoveredUrl(root, "raíz")]
        seen = {root}
        truncated = False
        for url, section in entries:
            if any(section.startswith(prefix) for prefix in excluded_sections):
                continue
            normalized = normalize_url(url)
            if normalized in seen or _host(normalized) != _host(root) or is_excluded(normalized):
                continue
            if len(selected) >= max_pages:
                truncated = True
                break
            if not await self._fetcher.allowed_by_robots(normalized):
                continue
            seen.add(normalized)
            selected.append(DiscoveredUrl(normalized, section))
        return Discovery(
            urls=tuple(selected),
            sections=sections,
            used_sitemap=used_sitemap,
            truncated=truncated,
        )

    # ── Sitemap ──────────────────────────────────────────────────────────
    async def _from_sitemaps(self, root: str) -> list[tuple[str, str]]:
        origin = urlunsplit((*urlsplit(root)[:2], "", "", ""))
        candidates = await self._robots_sitemaps(origin)
        candidates += [f"{origin}/{name}" for name in _SITEMAP_NAMES]
        for candidate in dict.fromkeys(candidates):
            entries = await self._read_sitemap(candidate, depth=0)
            if entries:
                return entries
        return []

    async def _robots_sitemaps(self, origin: str) -> list[str]:
        try:
            result = await self._fetcher.fetch(f"{origin}/robots.txt")
        except (WebFetchError, UnsafeUrlError):
            return []
        if result.status_code != 200:
            return []
        return [
            line.split(":", 1)[1].strip()
            for line in result.text.splitlines()
            if line.lower().startswith("sitemap:") and ":" in line
        ]

    async def _read_sitemap(self, url: str, *, depth: int) -> list[tuple[str, str]]:
        try:
            result = await self._fetcher.fetch(url)
        except (WebFetchError, UnsafeUrlError):
            return []
        if result.status_code != 200 or not result.body:
            return []
        body = result.body
        if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                return []
            if len(body) > _MAX_SITEMAP_BYTES:
                return []
        try:
            # `defusedxml` rechaza entidades externas y expansiones masivas.
            tree: Element = SafeElementTree.fromstring(body)  # pyright: ignore[reportUnknownMemberType]
        except Exception:  # noqa: BLE001 — XML inválido o malicioso: no es un sitemap
            return []
        name = url.rsplit("/", 1)[-1]
        children = _children(tree, "sitemap")
        if children and depth < 2:
            entries: list[tuple[str, str]] = []
            for child in children[:_MAX_CHILD_SITEMAPS]:
                entries.extend(await self._read_sitemap(child, depth=depth + 1))
            return entries
        return [(loc, name) for loc in _children(tree, "url")]

    # ── Links ────────────────────────────────────────────────────────────
    async def _from_links(self, root: str, limit: int) -> list[str]:
        found: list[str] = []
        seen = {root}
        frontier = [root]
        for _ in range(self._max_depth):
            following: list[str] = []
            for url in frontier:
                try:
                    result = await self._fetcher.fetch(url)
                except (WebFetchError, UnsafeUrlError):
                    continue
                await asyncio.sleep(self._delay_s)
                if not result.is_html:
                    continue
                for href in _HREF.findall(result.text):
                    target = normalize_url(urljoin(result.url, href))
                    if target in seen or _host(target) != _host(root):
                        continue
                    if not target.startswith(("http://", "https://")) or is_excluded(target):
                        continue
                    seen.add(target)
                    following.append(target)
                    found.append(target)
                    if len(found) >= limit:
                        return found
            frontier = following
            if not frontier:
                break
        return found
