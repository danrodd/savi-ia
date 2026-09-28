"""Importar desde la web (Fase 5): guarda SSRF, descarga, extracción y descubrimiento."""

# Los HTML y sitemaps de prueba son datos: partirlos empeora la lectura.
# ruff: noqa: E501

from __future__ import annotations

import gzip
import ipaddress
import socket
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from app.modules.company_knowledge.domain.entities.web_source import FetchResult
from app.modules.company_knowledge.domain.exceptions import UnsafeUrlError, WebFetchError
from app.modules.company_knowledge.domain.interfaces import WebFetcher
from app.modules.company_knowledge.infrastructure.web.content_extractor import (
    HybridContentExtractor,
)
from app.modules.company_knowledge.infrastructure.web.discovery import (
    SitemapAndLinksDiscoverer,
    is_excluded,
    normalize_url,
)
from app.modules.company_knowledge.infrastructure.web.safe_http import SafeHttpFetcher
from app.modules.company_knowledge.infrastructure.web.url_safety import (
    SafeTarget,
    resolve_safe_target,
    split_url,
)

# ── Guarda contra SSRF ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "ftp://sitio.com/archivo",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://sitio.com:8080/",
        "http://usuario:clave@sitio.com/",
        "http://",
    ],
)
def test_only_plain_http_urls_on_standard_ports(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        split_url(url)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.10",
        "169.254.169.254",  # metadatos de nube
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "224.0.0.1",
        "[::1]",
        "[fc00::1]",
        "[fe80::1]",
        "[::ffff:127.0.0.1]",  # IPv4 mapeada
    ],
)
async def test_internal_addresses_are_rejected(host: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await resolve_safe_target(f"http://{host}/")


async def test_a_public_address_is_accepted() -> None:
    target = await resolve_safe_target("https://93.184.215.14/precios")
    assert (target.host, target.port, str(target.ip)) == ("93.184.215.14", 443, "93.184.215.14")


def _fake_dns(monkeypatch: pytest.MonkeyPatch, *addresses: str) -> None:
    async def getaddrinfo(*_args: object, **_kwargs: object) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 443)) for a in addresses]

    import asyncio

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", getaddrinfo)


async def test_a_name_that_resolves_to_the_internal_network_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_dns(monkeypatch, "10.1.2.3")
    with pytest.raises(UnsafeUrlError, match="red interna"):
        await resolve_safe_target("https://intranet.empresa.com/")


async def test_one_internal_address_among_public_ones_is_enough_to_reject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_dns(monkeypatch, "93.184.215.14", "192.168.0.7")
    with pytest.raises(UnsafeUrlError):
        await resolve_safe_target("https://sitio.com/")


async def test_an_explicitly_allowed_intranet_host_can_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_dns(monkeypatch, "10.1.2.3")
    target = await resolve_safe_target("https://intranet.empresa.com/", ["intranet.empresa.com"])
    assert str(target.ip) == "10.1.2.3"


# ── Descarga ─────────────────────────────────────────────────────────────

_PUBLIC = {"sitio.test": "93.184.215.14", "otro.test": "93.184.215.15"}


async def _resolver(url: str, _allowed: Sequence[str]) -> SafeTarget:
    scheme, host, port = split_url(url)
    if host not in _PUBLIC:
        raise UnsafeUrlError("La dirección apunta a la red interna.")
    return SafeTarget(scheme, host, port, ipaddress.ip_address(_PUBLIC[host]))


def _fetcher(handler: Any, max_bytes: int = 1_000_000) -> SafeHttpFetcher:
    return SafeHttpFetcher(
        timeout_s=5,
        max_bytes=max_bytes,
        transport=httpx.MockTransport(handler),
        resolver=_resolver,
    )


async def test_the_request_goes_to_the_validated_ip_with_the_site_name() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, html="<p>hola</p>")

    result = await _fetcher(handler).fetch("https://sitio.test/precios?x=1")

    assert result.status_code == 200 and "hola" in result.text
    request = seen[0]
    assert request.url.host == "93.184.215.14"
    assert request.headers["host"] == "sitio.test"
    assert request.extensions["sni_hostname"] == "sitio.test"
    assert request.url.path == "/precios" and request.url.query == b"x=1"


async def test_gzip_responses_are_read_once() -> None:
    """Casi todos los sitios mandan gzip: descomprimirlo dos veces rompía la descarga."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=gzip.compress(b"<p>Tarifas vigentes</p>"),
            headers={"content-encoding": "gzip", "content-type": "text/html; charset=utf-8"},
        )

    result = await _fetcher(handler).fetch("https://sitio.test/tarifas")

    assert result.text == "<p>Tarifas vigentes</p>"


async def test_a_redirect_to_the_internal_network_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://interno.test/admin"})

    with pytest.raises(UnsafeUrlError):
        await _fetcher(handler).fetch("https://sitio.test/")


async def test_redirects_between_public_sites_are_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "sitio.test":
            return httpx.Response(301, headers={"location": "https://otro.test/nuevo"})
        return httpx.Response(200, html="<p>destino</p>")

    result = await _fetcher(handler).fetch("https://sitio.test/viejo")

    assert result.url == "https://otro.test/nuevo" and "destino" in result.text


async def test_endless_redirects_stop() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://sitio.test/otra-vez"})

    with pytest.raises(WebFetchError, match="redirige"):
        await _fetcher(handler).fetch("https://sitio.test/")


async def test_a_page_over_the_size_limit_is_cut() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000, headers={"content-type": "text/html"})

    with pytest.raises(WebFetchError, match="tope"):
        await _fetcher(handler, max_bytes=1000).fetch("https://sitio.test/")


async def test_conditional_request_reports_not_modified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"v1"'
        return httpx.Response(304)

    result = await _fetcher(handler).fetch("https://sitio.test/", etag='"v1"')

    assert result.not_modified


async def test_robots_txt_is_respected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /privado/\n")
        return httpx.Response(200, html="ok")

    fetcher = _fetcher(handler)

    assert await fetcher.allowed_by_robots("https://sitio.test/servicios")
    assert not await fetcher.allowed_by_robots("https://sitio.test/privado/actas")


# ── Extracción ───────────────────────────────────────────────────────────

extractor = HybridContentExtractor()


def test_pricing_cards_and_article_headers_survive_page_chrome_is_dropped() -> None:
    html = """
    <html><body>
      <header><nav>Inicio | Planes | Contacto</nav></header>
      <main>
        <h1>Planes</h1>
        <div class="card"><h3>Plan Pro</h3><p>$20 al mes</p></div>
        <div class="card"><h3>Plan Básico</h3><p>$5 al mes</p></div>
        <article><header><h2>Novedades de septiembre</h2></header><p>Nuevo plan.</p></article>
      </main>
      <footer>© 2026 Empresa. Todos los derechos reservados.</footer>
      <div class="cookie-banner">Usamos cookies</div>
    </body></html>
    """
    page = extractor.extract(html, "https://sitio.test/planes")

    assert page.title == "Planes"
    assert "Plan Pro" in page.markdown and "$20 al mes" in page.markdown
    assert "Novedades de septiembre" in page.markdown  # header DENTRO del artículo
    assert "Inicio | Planes" not in page.markdown
    assert "derechos reservados" not in page.markdown
    assert "cookies" not in page.markdown


def test_schema_org_product_becomes_text_with_the_currency_name() -> None:
    html = """
    <html><body><main><p>Comprar ahora</p></main>
    <script type="application/ld+json">
    {"@type": "Product", "name": "AMLODIPINO 5MG 10 TABLETAS", "sku": "45",
     "brand": {"@type": "Brand", "name": "Similares"},
     "offers": {"@type": "AggregateOffer", "lowPrice": 35, "priceCurrency": "MXN",
                "offers": [{"@type": "Offer", "price": 35, "priceCurrency": "MXN",
                            "availability": "http://schema.org/InStock"}]}}
    </script></body></html>
    """
    page = extractor.extract(html, "https://tienda.test/amlodipino/p")

    assert "- Producto: AMLODIPINO 5MG 10 TABLETAS" in page.markdown
    assert "- Precio: 35 pesos mexicanos (MXN)" in page.markdown
    assert "- Disponibilidad: disponible" in page.markdown


def test_invalid_json_ld_is_ignored() -> None:
    html = '<main><p>Texto</p></main><script type="application/ld+json">{no es json</script>'
    assert "Datos estructurados" not in extractor.extract(html, "https://sitio.test/").markdown


def test_prices_split_across_lines_are_joined() -> None:
    html = (
        "<main><p>PARACETAMOL 500 MG</p><span>$</span><div>8</div><div>.</div><div>00</div></main>"
    )
    assert "$8.00" in extractor.extract(html, "https://tienda.test/").markdown


def test_filler_text_is_flagged() -> None:
    html = (
        "<main><h1>FAQ</h1><p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p></main>"
    )
    assert extractor.extract(html, "https://sitio.test/faqs").looks_like_filler


def test_repeated_template_blocks_are_removed_and_kept_once() -> None:
    footer = "Calle 5 # 9-42, Bogotá\n311 531 0210"
    pages = {f"https://sitio.test/{i}": f"Contenido propio {i}.\n\n{footer}" for i in range(4)}

    cleaned, general = extractor.remove_boilerplate(pages)

    assert all(footer not in markdown for markdown in cleaned.values())
    assert cleaned["https://sitio.test/2"] == "Contenido propio 2."
    assert general == footer


def test_with_few_pages_nothing_is_treated_as_template() -> None:
    pages = {"https://sitio.test/a": "Igual", "https://sitio.test/b": "Igual"}
    assert extractor.remove_boilerplate(pages) == (pages, "")


# ── Descubrimiento ───────────────────────────────────────────────────────


class _FakeFetcher(WebFetcher):
    def __init__(self, pages: dict[str, tuple[str, bytes | str]], disallow: Sequence[str] = ()):
        self._pages = pages
        self._disallow = disallow

    async def fetch(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        if url not in self._pages:
            return FetchResult(url=url, status_code=404)
        content_type, body = self._pages[url]
        raw = body.encode() if isinstance(body, str) else body
        text = body if isinstance(body, str) else ""
        return FetchResult(url=url, status_code=200, content_type=content_type, body=raw, text=text)

    async def allowed_by_robots(self, url: str) -> bool:
        return not any(part in url for part in self._disallow)

    async def validate(self, url: str) -> None:
        return None


def _urlset(*locs: str) -> str:
    items = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def _index(*locs: str) -> str:
    items = "".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs)
    return (
        f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>'
    )


def _discoverer(fetcher: WebFetcher) -> SitemapAndLinksDiscoverer:
    return SitemapAndLinksDiscoverer(fetcher, max_depth=2, request_delay_s=0)


async def test_sitemap_index_gives_sections_and_honours_exclusions() -> None:
    root = "https://www.sitio.test/"
    fetcher = _FakeFetcher(
        {
            f"{root}robots.txt": ("text/plain", f"Sitemap: {root}wp-sitemap.xml\n"),
            f"{root}wp-sitemap.xml": (
                "application/xml",
                _index(f"{root}wp-sitemap-posts-page-1.xml", f"{root}wp-sitemap-posts-post-1.xml"),
            ),
            f"{root}wp-sitemap-posts-page-1.xml": (
                "application/xml",
                _urlset(
                    f"{root}planes/",
                    f"{root}cart-2/",
                    "https://otro-sitio.test/afuera",
                    f"{root}privado/acta",
                ),
            ),
            f"{root}wp-sitemap-posts-post-1.xml": (
                "application/xml",
                _urlset(f"{root}2021/bicicletas/", f"{root}2021/mas-bicicletas/"),
            ),
        },
        disallow=["/privado/"],
    )

    discovery = await _discoverer(fetcher).discover(
        root, max_pages=50, excluded_sections=["wp-sitemap-posts-post"]
    )

    assert discovery.used_sitemap
    assert discovery.sections == {
        "wp-sitemap-posts-page-1.xml": 4,
        "wp-sitemap-posts-post-1.xml": 2,
    }
    assert [u.url for u in discovery.urls] == [root, f"{root}planes/"]


async def test_the_page_limit_truncates_and_says_so() -> None:
    root = "https://sitio.test/"
    locs = [f"{root}p{i}" for i in range(10)]
    fetcher = _FakeFetcher({f"{root}sitemap.xml": ("application/xml", _urlset(*locs))})

    discovery = await _discoverer(fetcher).discover(root, max_pages=4, excluded_sections=[])

    assert len(discovery.urls) == 4 and discovery.truncated


async def test_gzipped_sitemaps_are_read() -> None:
    root = "https://sitio.test/"
    body = gzip.compress(_urlset(f"{root}servicios").encode())
    fetcher = _FakeFetcher({f"{root}sitemap.xml": ("application/x-gzip", body)})

    discovery = await _discoverer(fetcher).discover(root, max_pages=10, excluded_sections=[])

    assert [u.url for u in discovery.urls] == [root, f"{root}servicios"]


async def test_a_malicious_sitemap_is_ignored() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]><urlset><url><loc>&lol2;</loc></url></urlset>'
    )
    root = "https://sitio.test/"
    fetcher = _FakeFetcher(
        {
            f"{root}sitemap.xml": ("application/xml", bomb),
            root: ("text/html", '<a href="/contacto">Contacto</a>'),
        }
    )

    discovery = await _discoverer(fetcher).discover(root, max_pages=10, excluded_sections=[])

    assert not discovery.used_sitemap  # cae a seguir links
    assert [u.url for u in discovery.urls] == [root, f"{root}contacto"]


async def test_without_sitemap_links_of_the_same_site_are_followed() -> None:
    root = "https://sitio.test/"
    fetcher = _FakeFetcher(
        {
            root: (
                "text/html",
                '<a href="tarifas.html">T</a><a href="/css/estilo.css">c</a>'
                '<a href="https://externo.test/">x</a><a href="/docs/politica.pdf">p</a>',
            ),
            f"{root}tarifas.html": ("text/html", '<a href="/destinos.html">D</a>'),
            f"{root}destinos.html": ("text/html", "<p>fin</p>"),
        }
    )

    discovery = await _discoverer(fetcher).discover(root, max_pages=10, excluded_sections=[])

    assert [u.url for u in discovery.urls] == [
        root,
        f"{root}tarifas.html",
        f"{root}docs/politica.pdf",
        f"{root}destinos.html",
    ]
    assert discovery.sections == {"links": 3}


def test_url_normalization_and_exclusions() -> None:
    assert (
        normalize_url("HTTPS://Sitio.test/a?utm_source=x&id=3#top") == "https://sitio.test/a?id=3"
    )
    assert is_excluded("https://sitio.test/my-account-2/")
    assert is_excluded("https://sitio.test/tienda?add-to-cart=12")
    assert is_excluded("https://sitio.test/logo.png")
    assert not is_excluded("https://sitio.test/catalogo.pdf")
