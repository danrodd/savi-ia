"""Batería de ciclo de vida del conocimiento de la empresa.

Resultado y contexto: `docs/company_knowledge/bateria-ciclo-vida.md`.

Lo que las otras baterías no cubren: qué pasa DESPUÉS de subir un documento.

- **Reemplazar**: la versión nueva responde con el dato nuevo, en una
  conversación nueva y en una que ya estaba abierta, y se vuelve a leer con
  IA (no se reutiliza la lectura de la versión anterior).
- **Borrar**: deja de responder y de citarse en el acto, también en una
  conversación abierta, y desaparece del listado.
- **Cambiar el alcance**: quitarle un módulo o una base a un documento ya
  subido lo oculta en la siguiente pregunta para quien lo perdió, sin
  afectar a quien lo conserva. Cambiar el título cambia la cita.
- **Listado**: "¿qué documentos hay?" devuelve todos los que el usuario
  puede ver y ninguno más.
- **Fallos del proveedor**: con un modelo de lectura inexistente el
  documento no se queda "leyendo"; al corregirlo, "Leer con IA" lo
  recupera.
- **Archivos difíciles**: PDF con contraseña, PDF cortado, imagen con
  extensión .pdf y archivo vacío. Ninguno traba la cola.

Requiere lo mismo que `bateria_permisos_bases.py` (backend en
`localhost:8000`, usuarios de QA con clave 123) y conviene correrla después
de esa, porque el listado espera ver sus documentos.

    uv run python scripts/bateria_ciclo_vida.py

Cambia el modelo de lectura del proveedor activo durante la prueba de
fallos y lo restaura al terminar, aunque algo falle. Gasta tokens del
proveedor ACTIVO: con `gpt-6-luna`, ~US$0,03 por corrida.
"""

# ruff: noqa: E501

import argparse
import io
import json
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bateria_permisos_bases import API, NO_ACCESS, NOT_FOUND, Session, ask, norm, page
from pypdf import PdfReader, PdfWriter

CORPUS = Path(tempfile.gettempdir()) / "savi-corpus-ciclo-vida"
PREFIX = "[QA ciclo] "
BROKEN_MODEL = "modelo-inexistente-qa"
DEFAULT_BASE = "FARMACIAS_SIMILARES"

VIATICOS_V1 = (
    "POLITICA DE VIATICOS PV-22",
    [
        "Versión 1. Vigente desde el 1 de marzo de 2026.",
        "## Montos",
        "Viático diario nacional: 85.000 pesos.",
        "Hospedaje máximo por noche: 190.000 pesos.",
        "## Legalización",
        "Se legaliza dentro de los 5 días hábiles siguientes al viaje.",
    ],
)
VIATICOS_V2 = (
    "POLITICA DE VIATICOS PV-22",
    [
        "Versión 2. Vigente desde el 1 de septiembre de 2026.",
        "## Montos",
        "Viático diario nacional: 120.000 pesos.",
        "Hospedaje máximo por noche: 230.000 pesos.",
        "## Legalización",
        "Se legaliza dentro de los 5 días hábiles siguientes al viaje.",
    ],
)
PARQUEADERO = (
    "REGLAMENTO DE PARQUEADERO RP-05",
    [
        "## Cupos",
        "El parqueadero tiene 14 cupos para motos y 9 para carros.",
        "## Horario",
        "Abre de 6:00 a 21:00, de lunes a sábado.",
        "## Sanciones",
        "La multa por parquear en un cupo ajeno es de 35.000 pesos.",
    ],
)
CONTEO = (
    "PROCEDIMIENTO DE INVENTARIO CICLICO IC-31",
    [
        "## Frecuencia",
        "Cada semana se cuentan 40 referencias de la bodega principal.",
        "## Diferencias",
        "La tolerancia de diferencia entre el conteo y el sistema es del 0,8%.",
        "Diferencias mayores las revisa el auditor de inventarios.",
    ],
)
MANUAL_RECEPCION = (
    "MANUAL DE RECEPCION DE PEDIDOS MR-44",
    [
        "## Recepción",
        "Todo pedido se recibe con la orden de compra impresa.",
        "El tiempo máximo de descargue es de 45 minutos por vehículo.",
    ],
)


def pdf_bytes(content: tuple[str, list[str]]) -> bytes:
    buffer = io.BytesIO()
    page(*content).save(buffer, format="PDF", resolution=150, quality=75)
    return buffer.getvalue()


def encrypted_pdf(content: tuple[str, list[str]]) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes(content))))
    writer.encrypt("clave-qa")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def png_bytes(content: tuple[str, list[str]]) -> bytes:
    buffer = io.BytesIO()
    page(*content).save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class Result:
    id: str
    bloque: str
    descripcion: str
    problemas: list[str]
    detalle: dict[str, object] = field(default_factory=dict[str, object])


class Battery:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.admin = Session(client, "SAVIQA")
        self.bases = {
            b["code"]: b["id"]
            for b in client.get("/erp-databases/available", headers=self.admin.headers).json()
        }
        self.sessions: dict[str, Session] = {"SAVIQA": self.admin}
        self.results: list[Result] = []
        self.chat_cost = 0.0

    # ── Documentos ──────────────────────────────────────────────────────
    def cleanup(self) -> None:
        docs = self.client.get(
            "/admin/company-documents", headers=self.admin.headers, params={"limit": 200}
        ).json()
        for doc in docs:
            if doc["title"].startswith(PREFIX):
                self.client.delete(
                    f"/admin/company-documents/{doc['id']}", headers=self.admin.headers
                )

    def upload(
        self,
        title: str,
        filename: str,
        content: bytes,
        *,
        visibility: str = "all",
        modules: list[str] | None = None,
    ) -> httpx.Response:
        form: dict[str, str | list[str]] = {
            "title": PREFIX + title,
            "visibility": visibility,
            "all_databases": "true",
        }
        if modules:
            form["modules"] = modules
        return self.client.post(
            "/admin/company-documents",
            headers=self.admin.headers,
            files={"file": (filename, content, "application/pdf")},
            data=form,
        )

    def get(self, document_id: str) -> dict:
        return self.client.get(
            f"/admin/company-documents/{document_id}", headers=self.admin.headers
        ).json()

    def wait(self, document_id: str, timeout: float = 300) -> dict:
        started = time.time()
        while time.time() - started < timeout:
            doc = self.get(document_id)
            if doc["status"] not in ("pending", "processing"):
                return doc
            time.sleep(2)
        return self.get(document_id)

    def patch(self, document_id: str, **changes: object) -> dict:
        response = self.client.patch(
            f"/admin/company-documents/{document_id}", headers=self.admin.headers, json=changes
        )
        response.raise_for_status()
        return response.json()

    # ── Chat ────────────────────────────────────────────────────────────
    def session(self, login: str) -> Session:
        if login not in self.sessions:
            self.sessions[login] = Session(self.client, login)
        return self.sessions[login]

    def conversation(self, login: str, base: str) -> tuple[str, str]:
        # Farmacias Similares es la base por defecto; las demás se eligen
        # al iniciar sesión con `CODIGO@BASE`.
        if base != DEFAULT_BASE:
            login = f"{login}@{base}"
        response = self.client.post(
            "/conversations",
            json={"erp_database_id": self.bases[base]},
            headers=self.session(login).headers,
        )
        response.raise_for_status()
        return response.json()["id"], login

    def ask(self, chat: tuple[str, str], question: str) -> dict:
        conversation, login = chat
        answer = ask(self.client, self.session(login), conversation, question)
        self.chat_cost += answer["costo_usd"]
        return answer

    # ── Registro ────────────────────────────────────────────────────────
    def record(
        self, id_: str, bloque: str, descripcion: str, problems: list[str], **detalle: object
    ) -> None:
        self.results.append(Result(id_, bloque, descripcion, problems, dict(detalle)))
        flag = "OK   " if not problems else "FALLA"
        answer = str(detalle.get("respuesta", detalle.get("estado", "")))
        print(
            f"{flag} {id_} {descripcion[:60]:60} "
            + (f"{problems} " if problems else "")
            + "| "
            + answer.replace("\n", " ")[:120]
        )

    def check_answer(
        self,
        id_: str,
        bloque: str,
        descripcion: str,
        answer: dict,
        *,
        expected: list[list[str]] | None = None,
        forbidden: list[str] | None = None,
        cite: str | None = None,
        not_cited: list[str] | None = None,
        not_found: bool = False,
    ) -> None:
        text = norm(answer["respuesta"])
        problems: list[str] = []
        if answer["error"]:
            problems.append(f"error: {answer['error']}")
        if any(p in text for p in NO_ACCESS):
            problems.append("dijo 'no tengo acceso'")
        for group in expected or []:
            if not any(norm(alt) in text for alt in group):
                problems.append(f"falta {group}")
        for value in forbidden or []:
            if norm(value) in text:
                problems.append(f"dijo '{value}'")
        if cite and PREFIX + cite not in answer["fuentes"]:
            problems.append(f"no citó '{cite}'")
        for title in not_cited or []:
            if PREFIX + title in answer["fuentes"]:
                problems.append(f"citó '{title}'")
        if not_found and not any(p in text for p in NOT_FOUND):
            problems.append("no dijo que no lo encontró")
        self.record(
            id_,
            bloque,
            descripcion,
            problems,
            respuesta=answer["respuesta"],
            fuentes=answer["fuentes"],
            herramientas=answer["herramientas"],
        )

    def check_document(
        self, id_: str, bloque: str, descripcion: str, doc: dict, rules: list[tuple[str, bool]]
    ) -> None:
        problems = [message for message, ok in rules if not ok]
        self.record(
            id_,
            bloque,
            descripcion,
            problems,
            estado=f"status={doc.get('status')} code={doc.get('status_code')} lectura={doc.get('reading_method')} ia={doc.get('ai_page_count')} v={doc.get('version')} msg={doc.get('status_message')}",
        )

    # ── Escenarios ──────────────────────────────────────────────────────
    def replace(self) -> None:
        bloque = "reemplazar"
        created = self.upload("Política de viáticos", "viaticos.pdf", pdf_bytes(VIATICOS_V1))
        created.raise_for_status()
        doc_id = created.json()["id"]
        v1 = self.wait(doc_id)
        self.check_document(
            "R01",
            bloque,
            "versión 1 lista y leída con IA",
            v1,
            [
                ("no quedó lista", v1["status"] == "ready"),
                ("no se leyó con IA", v1["ai_page_count"] >= 1),
            ],
        )
        open_chat = self.conversation("QAINV", "FRAMI")
        answer = self.ask(open_chat, "¿cuánto es el viático diario nacional?")
        self.check_answer(
            "R02",
            bloque,
            "v1: responde 85.000",
            answer,
            expected=[["85.000", "85000"]],
            cite="Política de viáticos",
        )

        replaced = self.client.post(
            f"/admin/company-documents/{doc_id}/replace",
            headers=self.admin.headers,
            files={"file": ("viaticos_v2.pdf", pdf_bytes(VIATICOS_V2), "application/pdf")},
        )
        replaced.raise_for_status()
        v2 = self.wait(doc_id)
        self.check_document(
            "R03",
            bloque,
            "versión 2 lista, versión nueva y leída otra vez con IA",
            v2,
            [
                ("no quedó lista", v2["status"] == "ready"),
                ("no subió la versión", v2["version"] == v1["version"] + 1),
                ("no se volvió a leer con IA", v2["ai_page_count"] >= 1),
            ],
        )
        fresh = self.conversation("QAINV", "FRAMI")
        answer = self.ask(fresh, "¿de cuánto es el viático diario nacional?")
        self.check_answer(
            "R04",
            bloque,
            "conversación nueva: 120.000 y no 85.000",
            answer,
            expected=[["120.000", "120000"]],
            forbidden=["85.000", "85000"],
            cite="Política de viáticos",
        )
        # En la conversación abierta se pregunta un dato que no salió antes:
        # tiene que venir de la versión nueva.
        answer = self.ask(open_chat, "¿y el hospedaje máximo por noche?")
        self.check_answer(
            "R05",
            bloque,
            "conversación abierta: hospedaje de la v2 (230.000)",
            answer,
            expected=[["230.000", "230000"]],
            forbidden=["190.000", "190000"],
            cite="Política de viáticos",
        )

    def delete(self) -> None:
        bloque = "borrar"
        created = self.upload(
            "Reglamento de parqueadero", "parqueadero.pdf", pdf_bytes(PARQUEADERO)
        )
        created.raise_for_status()
        doc_id = created.json()["id"]
        self.wait(doc_id)
        open_chat = self.conversation("QAINV", "FRAMI")
        answer = self.ask(open_chat, "¿cuántos cupos para motos tiene el parqueadero?")
        self.check_answer(
            "B01",
            bloque,
            "antes de borrar: 14 cupos",
            answer,
            expected=[["14"]],
            cite="Reglamento de parqueadero",
        )

        response = self.client.delete(
            f"/admin/company-documents/{doc_id}", headers=self.admin.headers
        )
        self.record(
            "B02",
            bloque,
            "borrar responde 204",
            [] if response.status_code == 204 else [f"status {response.status_code}"],
            estado=response.status_code,
        )

        answer = self.ask(open_chat, "¿y cuánto es la multa por parquear en un cupo ajeno?")
        self.check_answer(
            "B03",
            bloque,
            "conversación abierta: ya no da la multa",
            answer,
            forbidden=["35.000", "35000"],
            not_cited=["Reglamento de parqueadero"],
            not_found=True,
        )
        fresh = self.conversation("QAINV", "FRAMI")
        answer = self.ask(fresh, "¿cuántos cupos de motos hay en el parqueadero?")
        self.check_answer(
            "B04",
            bloque,
            "conversación nueva: no lo encuentra",
            answer,
            forbidden=["14 cupos"],
            not_cited=["Reglamento de parqueadero"],
            not_found=True,
        )
        again = self.client.delete(f"/admin/company-documents/{doc_id}", headers=self.admin.headers)
        self.record(
            "B05",
            bloque,
            "borrar dos veces sigue en 204",
            [] if again.status_code == 204 else [f"status {again.status_code}"],
            estado=again.status_code,
        )

    def scope(self) -> None:
        bloque = "alcance"
        created = self.upload(
            "Procedimiento de inventario cíclico", "conteo.pdf", pdf_bytes(CONTEO)
        )
        created.raise_for_status()
        doc_id = created.json()["id"]
        self.wait(doc_id)
        cxc_chat = self.conversation("QACXC", "FARMACIAS_SIMILARES")
        answer = self.ask(
            cxc_chat, "¿cuántas referencias se cuentan por semana en el inventario cíclico?"
        )
        self.check_answer(
            "S01",
            bloque,
            "visible para todos: QACXC ve 40 referencias",
            answer,
            expected=[["40"]],
            cite="Procedimiento de inventario cíclico",
        )

        self.patch(doc_id, visibility="modules", modules=["INVENTARIO"])
        answer = self.ask(cxc_chat, "¿y cuál es la tolerancia de diferencia del conteo?")
        self.check_answer(
            "S02",
            bloque,
            "sin el módulo, conversación abierta: no da la tolerancia",
            answer,
            forbidden=["0,8", "0.8"],
            not_cited=["Procedimiento de inventario cíclico"],
            not_found=True,
        )
        fresh = self.conversation("QACXC", "FARMACIAS_SIMILARES")
        answer = self.ask(
            fresh, "¿cuántas referencias se cuentan por semana en el inventario cíclico?"
        )
        self.check_answer(
            "S03",
            bloque,
            "sin el módulo, conversación nueva: no lo encuentra",
            answer,
            forbidden=["40 referencias"],
            not_cited=["Procedimiento de inventario cíclico"],
            not_found=True,
        )
        inv_chat = self.conversation("QAINV", "FRAMI")
        answer = self.ask(inv_chat, "¿cuál es la tolerancia de diferencia en el conteo cíclico?")
        self.check_answer(
            "S04",
            bloque,
            "QAINV conserva el acceso: 0,8 %",
            answer,
            expected=[["0,8", "0.8"]],
            cite="Procedimiento de inventario cíclico",
        )

        self.patch(doc_id, all_databases=False, database_ids=[self.bases["SUR_ANDINA"]])
        # S04 ya dijo la tolerancia y quién revisa las diferencias: se pregunta
        # un dato que todavía no salió en la conversación.
        answer = self.ask(inv_chat, "¿y cuántas referencias se cuentan por semana?")
        self.check_answer(
            "S05",
            bloque,
            "limitado a Sur Andina, chat en FRAMI abierto: no responde",
            answer,
            forbidden=["40 referencias"],
            not_cited=["Procedimiento de inventario cíclico"],
            not_found=True,
        )
        sur_chat = self.conversation("QAINV", "SUR_ANDINA")
        answer = self.ask(sur_chat, "¿quién revisa las diferencias mayores del conteo cíclico?")
        self.check_answer(
            "S06",
            bloque,
            "en Sur Andina sí responde: el auditor",
            answer,
            expected=[["auditor"]],
            cite="Procedimiento de inventario cíclico",
        )

        self.patch(doc_id, title=PREFIX + "Procedimiento de conteo cíclico IC-31")
        answer = self.ask(
            self.conversation("QAINV", "SUR_ANDINA"),
            "¿cuántas referencias se cuentan por semana en el conteo cíclico?",
        )
        self.check_answer(
            "S07",
            bloque,
            "título cambiado: cita el título nuevo",
            answer,
            expected=[["40"]],
            cite="Procedimiento de conteo cíclico IC-31",
            not_cited=["Procedimiento de inventario cíclico"],
        )

    def listing(self) -> None:
        bloque = "listado"
        answer = self.ask(
            self.conversation("QAINV", "FRAMI"), "¿qué documentos de la empresa tenés cargados?"
        )
        self.check_answer(
            "L01",
            bloque,
            "QAINV en FRAMI: ve los suyos y ninguno ajeno",
            answer,
            expected=[
                ["devoluci"],
                ["viatic"],
                ["descuentos frami", "descuento frami", "descuentos - frami"],
            ],
            forbidden=["junta directiva", "jd-0917", "cartera", "sur andina", "parqueadero"],
        )
        answer = self.ask(
            self.conversation("QACXC", "FARMACIAS_SIMILARES"),
            "listame todas las políticas que hay cargadas",
        )
        self.check_answer(
            "L02",
            bloque,
            "QACXC en Farmacias: ve cartera, no devoluciones ni el acta",
            answer,
            expected=[["cartera"], ["viatic"]],
            forbidden=[
                "devoluci",
                "junta directiva",
                "jd-0917",
                "frami",
                "sur andina",
                "inventario ciclico",
                "conteo ciclico",
            ],
        )

    def provider_failure(self) -> None:
        bloque = "fallos"
        providers = self.client.get("/admin/llm-providers", headers=self.admin.headers).json()
        active = next(p for p in providers if p["is_active"])
        original = active["document_model"] or ""

        def save(document_model: str) -> httpx.Response:
            return self.client.put(
                f"/admin/llm-providers/{active['provider']}",
                headers=self.admin.headers,
                json={
                    "credential_kind": active["credential_kind"],
                    "chat_model": active["chat_model"],
                    "title_model": active["title_model"],
                    "document_model": document_model,
                },
            )

        saved = save(BROKEN_MODEL)
        try:
            self.record(
                "F01",
                bloque,
                "configurar un modelo de lectura inexistente",
                []
                if saved.status_code == 200
                else [f"status {saved.status_code}: {saved.text[:120]}"],
                estado=saved.status_code,
            )
            created = self.upload(
                "Manual de recepción", "recepcion.pdf", pdf_bytes(MANUAL_RECEPCION)
            )
            created.raise_for_status()
            doc_id = created.json()["id"]
            failed = self.wait(doc_id)
            self.check_document(
                "F02",
                bloque,
                "escaneado con el modelo roto: termina con aviso, no se traba",
                failed,
                [
                    ("se quedó procesando", failed["status"] not in ("pending", "processing")),
                    (
                        "no avisa el motivo",
                        failed["status"] == "ready" or bool(failed["status_message"]),
                    ),
                ],
            )
        finally:
            restored = save(original)
            self.record(
                "F03",
                bloque,
                "restaurar el modelo de lectura",
                [] if restored.status_code == 200 else [f"status {restored.status_code}"],
                estado=original or "(modelo de chat)",
            )

        response = self.client.post(
            f"/admin/company-documents/{doc_id}/read-with-ai", headers=self.admin.headers
        )
        recovered = (
            self.wait(doc_id)
            if response.status_code == 200
            else {"status": f"http {response.status_code}"}
        )
        self.check_document(
            "F04",
            bloque,
            "'Leer con IA' con el modelo correcto lo recupera",
            recovered,
            [
                ("no quedó listo", recovered["status"] == "ready"),
                ("no se leyó con IA", recovered.get("ai_page_count", 0) >= 1),
            ],
        )
        answer = self.ask(
            self.conversation("QAINV", "FRAMI"),
            "¿cuánto es el tiempo máximo de descargue de un vehículo?",
        )
        self.check_answer(
            "F05",
            bloque,
            "después de recuperarlo responde 45 minutos",
            answer,
            expected=[["45"]],
            cite="Manual de recepción",
        )

    def hard_files(self) -> None:
        bloque = "archivos"
        cases: list[tuple[str, str, str, bytes, Callable[[httpx.Response, dict], list[str]]]] = []

        def terminal_with_reason(code: str) -> Callable[[httpx.Response, dict], list[str]]:
            def rule(response: httpx.Response, doc: dict) -> list[str]:
                if response.status_code >= 400:
                    return [] if response.status_code < 500 else [f"status {response.status_code}"]
                problems = []
                if doc["status"] in ("pending", "processing"):
                    problems.append("se quedó procesando")
                if doc["status"] != "ready" and not doc.get("status_message"):
                    problems.append("sin mensaje")
                if code and doc["status"] != "ready" and doc.get("status_code") != code:
                    problems.append(f"código {doc.get('status_code')} en vez de {code}")
                return problems

            return rule

        def rejected(response: httpx.Response, _doc: dict) -> list[str]:
            if 400 <= response.status_code < 500:
                return []
            return [f"status {response.status_code}, esperaba 4xx"]

        good = pdf_bytes(MANUAL_RECEPCION)
        cases.append(
            (
                "A01",
                "PDF con contraseña",
                "protegido.pdf",
                encrypted_pdf(CONTEO),
                terminal_with_reason("pdf_encrypted"),
            )
        )
        cases.append(
            (
                "A02",
                "PDF cortado a la mitad",
                "cortado.pdf",
                good[: len(good) // 2],
                terminal_with_reason(""),
            )
        )
        cases.append(
            ("A03", "imagen PNG con extensión .pdf", "foto.pdf", png_bytes(CONTEO), rejected)
        )
        cases.append(("A04", "archivo vacío", "vacio.pdf", b"", rejected))
        for id_, title, filename, content, rule in cases:
            response = self.upload(title, filename, content)
            doc = (
                self.wait(response.json()["id"], timeout=180) if response.status_code < 300 else {}
            )
            problems = rule(response, doc)
            estado = (
                f"http {response.status_code} {response.text[:100]}"
                if response.status_code >= 300
                else f"status={doc['status']} code={doc.get('status_code')} msg={doc.get('status_message')}"
            )
            self.record(id_, bloque, title, problems, estado=estado)

        after = self.upload(
            "Viáticos después de los archivos difíciles",
            "viaticos_cola.pdf",
            pdf_bytes(VIATICOS_V2),
        )
        after.raise_for_status()
        doc = self.wait(after.json()["id"])
        self.check_document(
            "A05",
            bloque,
            "la cola sigue: el siguiente documento queda listo",
            doc,
            [("no quedó listo", doc["status"] == "ready")],
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=CORPUS)
    parser.add_argument("--solo", nargs="*", help="bloques a correr (por defecto, todos)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=API, timeout=120) as client:
        battery = Battery(client)
        settings = client.get(
            "/admin/company-documents/ai-reading", headers=battery.admin.headers
        ).json()
        if not settings.get("ai_reading_enabled"):
            raise SystemExit("Activá la lectura con IA antes de correr la batería")
        battery.cleanup()
        blocks = {
            "reemplazar": battery.replace,
            "borrar": battery.delete,
            "alcance": battery.scope,
            "listado": battery.listing,
            "fallos": battery.provider_failure,
            "archivos": battery.hard_files,
        }
        for name, run in blocks.items():
            if args.solo and name not in args.solo:
                continue
            print(f"\n── {name}")
            run()

        out = args.out / "resultado.json"
        out.write_text(
            json.dumps(
                [r.__dict__ for r in battery.results], ensure_ascii=False, indent=1, default=str
            ),
            encoding="utf-8",
        )
        print()
        for name in blocks:
            rows = [r for r in battery.results if r.bloque == name]
            if rows:
                print(f"  {name:11} {sum(not r.problemas for r in rows)}/{len(rows)}")
        passed = sum(not r.problemas for r in battery.results)
        print(
            f"\nRESULTADO {passed}/{len(battery.results)} · chat US${battery.chat_cost:.4f} · detalle en {out}"
        )


if __name__ == "__main__":
    main()
