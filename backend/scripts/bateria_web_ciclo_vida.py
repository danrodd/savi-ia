"""Batería de punta a punta de la importación desde la web (Fase 5).

Levanta un sitio de prueba en `http://127.0.0.1/` (una ferretería inventada
que el script modifica en vivo) y recorre el ciclo completo contra el
backend real:

- **SSRF**: localhost, metadatos de nube, IP privada, loopback no
  permitido, puerto no web, `file://`, usuario en la URL y una redirección
  del sitio hacia la red interna. Todo se rechaza.
- **No administradores**: no pueden usar la API de sitios.
- **Alta**: respeta `robots.txt`, descarta el carrito y excluye la sección
  "blog" elegida en la vista previa.
- **Cambio de precio**: al releer, versión nueva solo de esa página; el chat
  responde el precio nuevo en una conversación nueva y en una abierta, y
  cita el link.
- **Página borrada**: el primer 404 conserva lo último bueno; el segundo la
  da de baja y deja de citarse.
- **Permisos**: una página solo para cartera en una base la ve quien
  corresponde, no otro módulo ni otra base; abrir los permisos se propaga.
- **Baja**: borrar el sitio lo saca de las respuestas.

Requiere:
- el puerto 80 libre en esta máquina;
- el backend en `localhost:8000` con `127.0.0.1` permitido, porque la guarda
  SSRF bloquea la red interna:
      COMPANY_WEB_ALLOWED_PRIVATE_HOSTS='["127.0.0.1"]' uv run dev
- los usuarios de QA locales de `bateria_permisos_bases.py` (clave 123).

    uv run python scripts/bateria_web_ciclo_vida.py

Gasta tokens del proveedor ACTIVO solo en las preguntas del chat
(~12 preguntas).
"""

# ruff: noqa: E501

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from bateria_permisos_bases import API, NOT_FOUND, Session, norm

SITE_HOST = "127.0.0.1"
ROOT = f"http://{SITE_HOST}/"
BASE = "FARMACIAS_SIMILARES"
OTHER_BASE = "SUR_ANDINA"
TITLE = "[QA web] Ferretería El Tornillo"
CREDIT_TITLE = "[QA web] Política de crédito"

MENU = "Inicio · Precios · Garantía · Envíos · Blog · Contacto"
FOOTER = (
    "Ferretería El Tornillo S.A.S. · Calle 10 # 20-30, Medellín · "
    "Teléfono 604 555 0101 · Todos los derechos reservados."
)


def html(title: str, body: str) -> str:
    return (
        f"<html><head><title>{title} | El Tornillo</title></head><body>"
        f"<header><nav>{MENU}</nav></header>"
        f"<main><h1>{title}</h1>{body}</main>"
        f"<footer>{FOOTER}</footer></body></html>"
    )


def paragraph(*sentences: str) -> str:
    return "".join(f"<p>{s}</p>" for s in sentences)


PRICES_V1 = paragraph(
    "El taladro percutor TX-200 de 750 vatios cuesta 389.000 pesos con IVA incluido.",
    "La caja de tornillos drywall por 500 unidades cuesta 42.000 pesos.",
    "Los precios aplican para compras en tienda y en línea hasta agotar existencias.",
)
PRICES_V2 = PRICES_V1.replace("389.000", "429.000")

SITEMAP_INDEX = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>{ROOT}page-sitemap.xml</loc></sitemap>
<sitemap><loc>{ROOT}blog-sitemap.xml</loc></sitemap>
</sitemapindex>"""


def urlset(*paths: str) -> str:
    urls = "".join(f"<url><loc>{ROOT}{p}</loc></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def initial_site() -> dict[str, tuple[int, str, str]]:
    return {
        "robots.txt": (
            200,
            "text/plain",
            f"User-agent: *\nDisallow: /privado/\nSitemap: {ROOT}sitemap_index.xml\n",
        ),
        "sitemap_index.xml": (200, "application/xml", SITEMAP_INDEX),
        "page-sitemap.xml": (
            200,
            "application/xml",
            urlset("", "precios", "garantia", "envios", "privado/costos", "carrito"),
        ),
        "blog-sitemap.xml": (
            200,
            "application/xml",
            urlset("blog/pintar-paredes", "blog/elegir-broca"),
        ),
        "": (
            200,
            "text/html",
            html(
                "Bienvenidos",
                paragraph(
                    "Somos una ferretería familiar con tres sedes en Medellín desde 1998.",
                    "Vendemos herramientas eléctricas, tornillería, pinturas y materiales de construcción.",
                    "Atendemos de lunes a sábado de 7 de la mañana a 6 de la tarde y los domingos hasta el mediodía.",
                ),
            ),
        ),
        "precios": (200, "text/html", html("Precios destacados", PRICES_V1)),
        "garantia": (
            200,
            "text/html",
            html(
                "Garantía",
                paragraph(
                    "Todas las herramientas eléctricas tienen garantía de 18 meses por defectos de fábrica.",
                    "Para hacerla válida se presenta la factura y la herramienta completa en cualquier sede.",
                ),
            ),
        ),
        "envios": (
            200,
            "text/html",
            html(
                "Envíos",
                paragraph(
                    "Los envíos dentro del área metropolitana son gratis en compras mayores a 150.000 pesos.",
                    "Los pedidos hechos antes de las 2 de la tarde se entregan el mismo día hábil.",
                ),
            ),
        ),
        "privado/costos": (
            200,
            "text/html",
            html(
                "Costos internos",
                paragraph(
                    "El margen interno del taladro TX-200 es del 42 por ciento sobre el costo del proveedor.",
                    "Esta página es solo para el equipo de compras y no debe publicarse a clientes.",
                ),
            ),
        ),
        "carrito": (200, "text/html", html("Carrito", paragraph("Tu carrito está vacío. " * 10))),
        "blog/pintar-paredes": (
            200,
            "text/html",
            html(
                "Cómo pintar paredes",
                paragraph(
                    "Para pintar una pared primero se lija, se limpia el polvo y se aplica una base selladora.",
                    "Luego se dan dos manos de pintura con rodillo de felpa media, esperando cuatro horas entre manos.",
                ),
            ),
        ),
        "blog/elegir-broca": (
            200,
            "text/html",
            html(
                "Cómo elegir una broca",
                paragraph(
                    "Las brocas para concreto tienen punta de tungsteno y se usan con el percutor activado.",
                    "Para madera conviene una broca de punta de centrado que evita que el agujero se desvíe.",
                ),
            ),
        ),
        "credito": (
            200,
            "text/html",
            html(
                "Política de crédito",
                paragraph(
                    "El cupo de crédito para clientes empresariales es de hasta 8 millones de pesos a 45 días.",
                    "Para abrir el crédito se requiere RUT, cámara de comercio y dos referencias comerciales.",
                ),
            ),
        ),
        # Redirección del sitio hacia los metadatos de la nube: la guarda
        # debe validar cada salto, no solo la primera dirección.
        "salir": (302, "text/html", "http://169.254.169.254/latest/meta-data/"),
    }


SITE: dict[str, tuple[int, str, str]] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0].split("#")[0].lstrip("/")
        status, content_type, body = SITE.get(path, (404, "text/html", html("No existe", "")))
        self.send_response(status)
        if status in (301, 302):
            self.send_header("Location", body)
            body = ""
        payload = body.encode()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


# ── Resultados ────────────────────────────────────────────────────────────


@dataclass
class Report:
    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, ok, detail))
        print(f"{'OK   ' if ok else 'FALLA'} {name}" + (f" | {detail}" if detail else ""))
        return ok


# ── Utilidades contra la API ─────────────────────────────────────────────


def wait_for(predicate: Callable[[], Any], timeout: float, what: str) -> Any:
    started = time.time()
    while time.time() - started < timeout:
        value = predicate()
        if value:
            return value
        time.sleep(2)
    raise SystemExit(f"Tiempo agotado esperando: {what}")


def source_detail(client: httpx.Client, admin: Session, source_id: str) -> dict:
    return client.get(f"/admin/company-web-sources/{source_id}", headers=admin.headers).json()


def wait_crawled(client: httpx.Client, admin: Session, source_id: str) -> dict:
    """Espera a que termine el rastreo y a que todas sus páginas estén indexadas."""

    def crawled() -> dict | None:
        detail = source_detail(client, admin, source_id)
        return detail if detail["status"] in ("ready", "failed") else None

    detail = wait_for(crawled, 300, "el rastreo del sitio")

    def indexed() -> bool:
        for page in detail["pages"]:
            if page["status"] == "removed":
                continue
            doc = client.get(
                f"/admin/company-documents/{page['document_id']}", headers=admin.headers
            )
            if doc.status_code == 200 and doc.json()["status"] in ("pending", "processing"):
                return False
        return True

    wait_for(indexed, 300, "el procesamiento de las páginas")
    return detail


def pages_by_path(detail: dict) -> dict[str, dict]:
    return {page["url"].removeprefix(ROOT): page for page in detail["pages"]}


def new_conversation(client: httpx.Client, session: Session, base_id: str) -> str:
    response = client.post(
        "/conversations", json={"erp_database_id": base_id}, headers=session.headers
    )
    response.raise_for_status()
    return response.json()["id"]


def ask(client: httpx.Client, session: Session, conversation: str, question: str) -> dict:
    text: list[str] = []
    with client.stream(
        "POST",
        "/chat",
        json={"conversation_id": conversation, "action": "send", "message": question},
        headers=session.headers,
        timeout=300,
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "text_delta":
                    text.append(event["text"])
    replies: list[dict] = []
    for _ in range(20):
        detail = client.get(f"/conversations/{conversation}", headers=session.headers).json()
        replies = [m for m in detail["messages"] if m["role"] == "assistant"]
        if len(replies) and replies[-1].get("content"):
            break
        time.sleep(0.5)
    sources = replies[-1].get("sources") or [] if replies else []
    return {"text": "".join(text), "sources": sources}


def mentions(answer: dict, *needles: str) -> bool:
    text = norm(answer["text"]).replace(".", "").replace(" ", "")
    return any(norm(n).replace(".", "").replace(" ", "") in text for n in needles)


def cites(answer: dict, path: str) -> bool:
    return any((s.get("url") or "") == f"{ROOT}{path}" for s in answer["sources"])


def denies(answer: dict) -> bool:
    return any(phrase in norm(answer["text"]) for phrase in NOT_FOUND)


def short(answer: dict) -> str:
    urls = [s.get("url") for s in answer["sources"]]
    return answer["text"].replace("\n", " ")[:140] + f" | fuentes={urls}"


# ── Bloques ───────────────────────────────────────────────────────────────


def cleanup(client: httpx.Client, admin: Session) -> None:
    for source in client.get("/admin/company-web-sources", headers=admin.headers).json():
        if source["url"].startswith(ROOT):
            client.delete(f"/admin/company-web-sources/{source['id']}", headers=admin.headers)


def check_ssrf(client: httpx.Client, admin: Session, report: Report) -> None:
    unsafe = {
        "localhost": "http://localhost/",
        "metadatos de nube": "http://169.254.169.254/latest/meta-data/",
        "IP privada": "http://192.168.1.10/",
        "loopback no permitido": "http://127.0.0.2/",
        "puerto de la base de datos": f"http://{SITE_HOST}:5433/",
        "file://": "file:///etc/passwd",
        "usuario en la URL": f"http://admin:clave@{SITE_HOST}/",
        "IPv6 local": "http://[::1]/",
    }
    for name, url in unsafe.items():
        for action in ("preview", ""):
            path = "/admin/company-web-sources" + (f"/{action}" if action else "")
            body = {"url": url, "mode": "page", "max_pages": 5}
            response = client.post(path, headers=admin.headers, json=body)
            report.check(
                f"SSRF {name} ({'vista previa' if action else 'alta'})",
                response.status_code == 422,
                f"{response.status_code} {response.json().get('detail', '')}"[:120],
            )
    response = client.post(
        "/admin/company-web-sources/preview",
        headers=admin.headers,
        json={"url": f"{ROOT}salir", "mode": "page", "max_pages": 5},
    )
    report.check(
        "SSRF redirección del sitio hacia la red interna",
        response.status_code == 422,
        f"{response.status_code} {response.json().get('detail', '')}"[:120],
    )


def check_non_admin(client: httpx.Client, user: Session, report: Report) -> None:
    listing = client.get("/admin/company-web-sources", headers=user.headers)
    created = client.post(
        "/admin/company-web-sources",
        headers=user.headers,
        json={"url": ROOT, "mode": "site"},
    )
    report.check(
        "Un usuario no administrador no puede listar ni crear sitios",
        listing.status_code == 403 and created.status_code == 403,
        f"listar={listing.status_code} crear={created.status_code}",
    )


def main() -> None:
    SITE.update(initial_site())
    try:
        server = ThreadingHTTPServer((SITE_HOST, 80), Handler)
    except OSError as exc:
        raise SystemExit(f"No se pudo abrir el puerto 80: {exc}") from exc
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = Report()

    with httpx.Client(base_url=API, timeout=180, headers={"Connection": "close"}) as client:
        admin = Session(client, "SAVIQA")
        bases = {
            b["code"]: b["id"]
            for b in client.get("/erp-databases/available", headers=admin.headers).json()
        }
        cleanup(client, admin)

        probe = client.post(
            "/admin/company-web-sources/preview",
            headers=admin.headers,
            json={"url": ROOT, "mode": "site", "max_pages": 50},
        )
        if probe.status_code != 200:
            raise SystemExit(
                f"El backend no lee el sitio de prueba ({probe.status_code} {probe.text[:200]}). "
                "¿Arrancó con COMPANY_WEB_ALLOWED_PRIVATE_HOSTS='[\"127.0.0.1\"]'?"
            )

        print("\n== SSRF y acceso ==")
        check_ssrf(client, admin, report)
        check_non_admin(client, Session(client, f"QAINV@{BASE}"), report)

        print("\n== Vista previa y alta ==")
        preview = probe.json()
        report.check(
            "La vista previa encuentra el mapa del sitio y sus secciones",
            preview["used_sitemap"]
            and {"page-sitemap.xml", "blog-sitemap.xml"} <= set(preview["sections"]),
            f"secciones={preview['sections']} páginas={preview['page_count']}",
        )
        created = client.post(
            "/admin/company-web-sources",
            headers=admin.headers,
            json={
                "url": ROOT,
                "mode": "site",
                "title": TITLE,
                "refresh": "manual",
                "max_pages": 50,
                "excluded_sections": ["blog-sitemap.xml"],
            },
        )
        created.raise_for_status()
        site_id = created.json()["id"]
        detail = wait_crawled(client, admin, site_id)
        pages = pages_by_path(detail)
        report.check(
            "El sitio queda listo", detail["status"] == "ready", detail["status_message"] or ""
        )
        report.check(
            "Importa las páginas públicas",
            {"", "precios", "garantia", "envios"} <= set(pages),
            f"páginas={sorted(pages)}",
        )
        report.check(
            "Respeta robots.txt (no lee /privado/)", not any(p.startswith("privado") for p in pages)
        )
        report.check("Descarta el carrito", "carrito" not in pages)
        report.check(
            "Excluye la sección blog elegida", not any(p.startswith("blog") for p in pages)
        )
        report.check(
            "Guarda una sola vez el menú y el pie repetidos",
            "#informacion-general" in pages,
            f"páginas={sorted(pages)}",
        )

        print("\n== Chat con el sitio ==")
        inv = Session(client, f"QAINV@{BASE}")
        open_conversation = new_conversation(client, inv, bases[BASE])
        answer = ask(
            client,
            inv,
            open_conversation,
            "¿Cuánto cuesta el taladro percutor TX-200 en la ferretería El Tornillo?",
        )
        report.check(
            "Responde el precio del sitio", mentions(answer, "389.000", "389000"), short(answer)
        )
        report.check("Cita la página con su link", cites(answer, "precios"), short(answer))
        answer = ask(
            client,
            inv,
            new_conversation(client, inv, bases[BASE]),
            "¿Cuál es el margen interno del taladro TX-200 en El Tornillo?",
        )
        report.check(
            "No conoce lo que robots.txt excluye",
            not mentions(answer, "42 por ciento", "42%", "42 %"),
            short(answer),
        )
        answer = ask(
            client,
            inv,
            new_conversation(client, inv, bases[BASE]),
            "¿Cuál es el teléfono de la ferretería El Tornillo?",
        )
        report.check(
            "Responde el teléfono del pie de página, citando la información general",
            # El fragmento no existe en el sitio real: la cita lleva a la
            # portada, que es donde el visitante ve ese pie.
            mentions(answer, "604 555 0101", "6045550101")
            and any(
                s.get("title") == "Información general del sitio" and s.get("url") == ROOT
                for s in answer["sources"]
            ),
            short(answer),
        )

        print("\n== Cambio de precio ==")
        precios_doc = pages["precios"]["document_id"]
        SITE["precios"] = (200, "text/html", html("Precios destacados", PRICES_V2))
        client.post(
            f"/admin/company-web-sources/{site_id}/refresh", headers=admin.headers
        ).raise_for_status()
        detail = wait_crawled(client, admin, site_id)
        pages = pages_by_path(detail)
        statuses = {path: page["status"] for path, page in pages.items()}
        report.check(
            "Solo la página de precios cambia",
            statuses.get("precios") == "imported"
            and all(s == "unchanged" for p, s in statuses.items() if p != "precios"),
            f"estados={statuses}",
        )
        document = client.get(
            f"/admin/company-documents/{precios_doc}", headers=admin.headers
        ).json()
        report.check(
            "Precios pasa a la versión 2 en el mismo documento",
            document["version"] == 2,
            f"versión={document['version']}",
        )
        answer = ask(
            client,
            inv,
            new_conversation(client, inv, bases[BASE]),
            "¿Cuánto cuesta el taladro percutor TX-200 en El Tornillo?",
        )
        report.check(
            "Conversación nueva: responde el precio nuevo",
            mentions(answer, "429.000", "429000") and not mentions(answer, "389.000", "389000"),
            short(answer),
        )
        answer = ask(
            client,
            inv,
            open_conversation,
            "¿Y ahora cuánto cuesta ese taladro? Revisa de nuevo el sitio.",
        )
        report.check(
            "Conversación abierta: responde el precio nuevo",
            mentions(answer, "429.000", "429000"),
            short(answer),
        )

        print("\n== Página borrada ==")
        garantia_doc = pages["garantia"]["document_id"]
        SITE.pop("garantia")
        client.post(
            f"/admin/company-web-sources/{site_id}/refresh", headers=admin.headers
        ).raise_for_status()
        detail = wait_crawled(client, admin, site_id)
        page = pages_by_path(detail).get("garantia", {})
        report.check(
            "Primer 404: la página se conserva con error",
            page.get("status") == "failed",
            f"estado={page.get('status')} detalle={page.get('status_detail')}",
        )
        answer = ask(
            client,
            inv,
            new_conversation(client, inv, bases[BASE]),
            "¿Cuántos meses de garantía tienen las herramientas eléctricas en El Tornillo?",
        )
        report.check(
            "Primer 404: sigue respondiendo lo último bueno",
            mentions(answer, "18 meses"),
            short(answer),
        )
        client.post(
            f"/admin/company-web-sources/{site_id}/refresh", headers=admin.headers
        ).raise_for_status()
        detail = wait_crawled(client, admin, site_id)
        report.check(
            "Segundo 404: la página se da de baja",
            "garantia" not in pages_by_path(detail)
            or pages_by_path(detail)["garantia"]["status"] == "removed",
            f"páginas={sorted(pages_by_path(detail))}",
        )
        gone = client.get(f"/admin/company-documents/{garantia_doc}", headers=admin.headers)
        report.check("Su documento se elimina", gone.status_code == 404, f"{gone.status_code}")
        answer = ask(
            client,
            inv,
            new_conversation(client, inv, bases[BASE]),
            "¿Cuántos meses de garantía tienen las herramientas eléctricas en El Tornillo?",
        )
        report.check(
            "Ya no responde ni cita la garantía",
            not mentions(answer, "18 meses") and not cites(answer, "garantia"),
            short(answer),
        )

        print("\n== Permisos ==")
        created = client.post(
            "/admin/company-web-sources",
            headers=admin.headers,
            json={
                "url": f"{ROOT}credito",
                "mode": "page",
                "title": CREDIT_TITLE,
                "refresh": "manual",
                "visibility": "modules",
                "modules": ["CUENTACOBRAR"],
                "all_databases": False,
                "database_ids": [bases[BASE]],
            },
        )
        created.raise_for_status()
        credit_id = created.json()["id"]
        wait_crawled(client, admin, credit_id)
        question = "¿Cuál es el cupo de crédito para clientes empresariales en El Tornillo?"
        cxc = Session(client, f"QACXC@{BASE}")
        answer = ask(client, cxc, new_conversation(client, cxc, bases[BASE]), question)
        report.check(
            "Cartera en la base correcta la ve",
            mentions(answer, "8 millones", "8.000.000"),
            short(answer),
        )
        answer = ask(client, inv, new_conversation(client, inv, bases[BASE]), question)
        report.check(
            "Otro módulo no la ve", not mentions(answer, "8 millones", "8.000.000"), short(answer)
        )
        cxc_other = Session(client, f"QACXC@{OTHER_BASE}")
        answer = ask(
            client, cxc_other, new_conversation(client, cxc_other, bases[OTHER_BASE]), question
        )
        report.check(
            "Cartera en otra base no la ve",
            not mentions(answer, "8 millones", "8.000.000"),
            short(answer),
        )
        client.patch(
            f"/admin/company-web-sources/{credit_id}",
            headers=admin.headers,
            json={"visibility": "all", "modules": []},
        ).raise_for_status()
        answer = ask(client, inv, new_conversation(client, inv, bases[BASE]), question)
        report.check(
            "Al abrir los permisos, otro módulo ya la ve",
            mentions(answer, "8 millones", "8.000.000"),
            short(answer),
        )

        print("\n== Baja del sitio ==")
        client.delete(
            f"/admin/company-web-sources/{site_id}", headers=admin.headers
        ).raise_for_status()
        gone = client.get(f"/admin/company-documents/{precios_doc}", headers=admin.headers)
        report.check(
            "Borrar el sitio elimina sus páginas", gone.status_code == 404, f"{gone.status_code}"
        )
        answer = ask(
            client,
            inv,
            new_conversation(client, inv, bases[BASE]),
            "¿Cuánto cuesta el taladro percutor TX-200 en El Tornillo?",
        )
        report.check(
            "Ya no responde el precio",
            not mentions(answer, "429.000", "429000") and not cites(answer, "precios"),
            short(answer),
        )
        client.delete(f"/admin/company-web-sources/{credit_id}", headers=admin.headers)

    server.shutdown()
    failed = [name for name, ok, _ in report.results if not ok]
    print(f"\n{len(report.results) - len(failed)} de {len(report.results)} comprobaciones OK")
    for name in failed:
        print(f"  FALLA: {name}")


if __name__ == "__main__":
    main()
