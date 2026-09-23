"""Batería de punta a punta de la lectura de PDF con IA.

Resultado y contexto: `docs/company_knowledge/bateria-lectura-ia.md`.

Uso, con el backend corriendo en `localhost:8000` y un administrador
`admin`/`123` (desarrollo):

    uv run python scripts/bateria_lectura_ia.py          # sube y pregunta
    uv run python scripts/bateria_lectura_ia.py --reusar # no vuelve a subir

Gasta tokens del proveedor ACTIVO: con `gpt-6-luna`, ~US$0,03 la lectura y
~US$0,015 las preguntas.

0. Descarga el corpus público (7 PDF, 47 páginas) a una carpeta temporal.
1. Sube los 7 PDF del corpus por la API (lectura con IA activa, proveedor
   activo) y espera a que queden listos.
2. Hace 22 preguntas por el chat, cada una en una conversación nueva.
3. Verifica cada respuesta: el dato esperado, la cita del documento correcto
   y que no haya rechazos tipo "no tengo acceso". Las 2 preguntas negativas
   verifican que SAVI diga que no lo encuentra en lugar de inventar.

Los valores esperados salen de `pypdf` (documentos digitales) o de mirar la
imagen (escaneos), nunca de la transcripción de la IA.
"""

# Las URL del corpus y las preguntas son datos: partirlas en varias líneas
# empeora la lectura de la tabla.
# ruff: noqa: E501

import json
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

import httpx

API = "http://localhost:8000"
CORPUS = Path(tempfile.gettempdir()) / "savi-corpus-lectura-ia"
OUT = CORPUS / "resultado.json"

URLS = {
    "potabon_k_camscanner.pdf": "https://croper-production.s3.amazonaws.com/product_provider_files/files/000/015/127/original/ficha_tecnica_Potabon_K_20200304090357.pdf.pdf",
    "queretaro_escaneados.pdf": "https://municipiodequeretaro.gob.mx/municipio/repositorios/transparencia/a67/1T22/sds/84S.pdf",
    "homedepot_camscanner.pdf": "https://images.thdstatic.com/catalog/pdfImages/51/51960b5c-3c93-4bf5-8499-87edb6b831b2.pdf",
    "rotoplas_ft.pdf": "https://rotoplas.vteximg.com.br/arquivos/FT-320003.pdf?v=638201110020170000",
    "cisealco_stb.pdf": "https://cisealco.com/catalogos/cat_bomb_sixteam.pdf",
    "canarias_vivienda.pdf": "https://www3.gobiernodecanarias.org/medusa/ecoblog/mmormarf/files/2015/04/instalacion-electrica-vivienda-2.pdf",
    "aemps_ficha.pdf": "https://cima.aemps.es/cima/pdfs/es/ft/64154/FichaTecnica_64154.html.pdf",
}


def download_corpus() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        follow_redirects=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"}
    ) as web:
        for name, url in URLS.items():
            target = CORPUS / name
            if target.exists():
                continue
            response = web.get(url)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise SystemExit(f"{name}: la URL ya no devuelve un PDF ({url})")
            target.write_bytes(response.content)


DOCS = {
    "potabon": ("potabon_k_camscanner.pdf", "Ficha técnica Potabon K", "Escaneo CamScanner, tabla"),
    "queretaro": (
        "queretaro_escaneados.pdf",
        "Solicitud de licencia de construcción Querétaro",
        "Foto de formulario",
    ),
    "rubbermaid": (
        "homedepot_camscanner.pdf",
        "Guía de instalación de repisas Rubbermaid",
        "Diagrama escaneado",
    ),
    "rotoplas": ("rotoplas_ft.pdf", "Ficha técnica bombas Rotoplas TCP", "Digital con curva"),
    "cisealco": ("cisealco_stb.pdf", "Catálogo bombas Cisealco STB", "Tablas y curvas"),
    "canarias": ("canarias_vivienda.pdf", "Instalación eléctrica de vivienda", "Planos y esquemas"),
    "simdax": ("aemps_ficha.pdf", "Ficha técnica Simdax", "Texto digital denso"),
}

# (id, documento, pregunta, [grupos de alternativas: TODOS los grupos deben aparecer])
QUESTIONS = [
    (
        "P01",
        "potabon",
        "¿Qué porcentaje de citronela contiene el Potabon K?",
        [["3,0%", "3.0%", "3%", "3,0 %", "3 %"]],
    ),
    (
        "P02",
        "potabon",
        "¿En qué presentaciones se vende el Potabon K?",
        [["20"], ["10"], ["4"], ["litro"]],
    ),
    ("P03", "potabon", "¿Cuál es el pH de la solución al 5% del Potabon K?", [["6"], ["7"]]),
    (
        "P04",
        "queretaro",
        "En la solicitud de licencia de construcción de Querétaro, ¿cuál es la superficie del predio?",
        [["220.17", "220,17"]],
    ),
    (
        "P05",
        "queretaro",
        "En la solicitud de licencia de construcción de Querétaro, ¿cuál es el total de metros cuadrados de construcción?",
        [["247.34", "247,34"]],
    ),
    (
        "P06",
        "rubbermaid",
        "Según la guía de instalación de Rubbermaid, ¿cada cuánto se atornilla el montante a los parantes?",
        [["16"]],
    ),
    (
        "P07",
        "rubbermaid",
        "Según la guía de Rubbermaid, ¿cuánto peso soporta la repisa?",
        [["50"], ["22.7", "22,7"]],
    ),
    (
        "P08",
        "rotoplas",
        "¿Cuál es el caudal máximo de la bomba Rotoplas TCP158 de 1 HP?",
        [[r"re:\b6\s*m"]],
    ),
    ("P09", "rotoplas", "¿Qué corriente máxima tiene la bomba Rotoplas TCP130?", [["2.7", "2,7"]]),
    ("P10", "rotoplas", "¿De qué material es el impulsor de las bombas Rotoplas TCP?", [["noryl"]]),
    ("P11", "cisealco", "¿Cuánto pesa la bomba Cisealco STB1 300?", [[r"re:\b33\s*(kg|kilo)"]]),
    (
        "P12",
        "cisealco",
        "¿Qué potencia en HP tiene la bomba Cisealco STB2 750 T?",
        [["7,5", "7.5"]],
    ),
    (
        "P13",
        "cisealco",
        "¿Cuál es la temperatura máxima del líquido para las bombas Cisealco STB?",
        [["90"]],
    ),
    (
        "P14",
        "cisealco",
        "¿De qué material es el sello mecánico de las bombas Cisealco STB?",
        [["carbon"], ["ceramica"]],
    ),
    (
        "P15",
        "canarias",
        "¿Qué tipos de esquemas se usan para representar la instalación eléctrica de una vivienda?",
        [["topografico"], ["multifilar"], ["unifilar"]],
    ),
    (
        "P16",
        "canarias",
        "En una instalación eléctrica de vivienda, ¿qué se necesita para encender una bombilla desde tres puntos diferentes?",
        [["cruce"]],
    ),
    (
        "P17",
        "simdax",
        "¿Cuántos mg de levosimendán contiene un vial de 5 ml de Simdax?",
        [["12,5", "12.5"]],
    ),
    (
        "P18",
        "simdax",
        "¿Cuál es la dosis de carga inicial de Simdax?",
        [["6"], ["12"], ["microgramo", "mcg", "µg"]],
    ),
    (
        "P19",
        "simdax",
        "¿Durante cuántos días se recomienda monitorizar con Simdax a pacientes con daño renal o hepático leve a moderado?",
        [["5"]],
    ),
    ("P20", "simdax", "¿Cuánto alcohol (etanol) contiene Simdax por ml?", [["785"]]),
    ("N01", "potabon", "¿Cuál es el precio de venta del Potabon K?", "negativa"),
    ("N02", "cisealco", "¿Cuántos empleados tiene la empresa Cisealco?", "negativa"),
]

NO_ACCESS = [
    "no tengo acceso",
    "no puedo acceder",
    "no cuento con acceso",
    "no tengo permiso",
    "no dispongo de acceso",
    "no tengo la capacidad",
]
HEDGES = [
    "pareceria",
    "no indica explicitamente",
    "no se indica explicitamente",
    "por la nomenclatura",
]
OFF_TOPIC = ["solo puedo ayudarte con temas"]
NOT_FOUND = [
    "no encontr",
    "no aparece",
    "no se indica",
    "no indica",
    "no especifica",
    "no se especifica",
    "no figura",
    "no incluye",
    "no menciona",
    "no se menciona",
    "no tengo informacion",
    "no hay informacion",
    "no contiene",
    "no esta",
    "no dispongo de informacion",
    "no cuento con",
]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def has(text: str, alternative: str) -> bool:
    if alternative.startswith("re:"):
        return re.search(alternative[3:], norm(text)) is not None
    return norm(alternative) in norm(text)


def login(client: httpx.Client) -> dict[str, str]:
    token = client.post("/auth/login", json={"login": "admin", "password": "123"}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def upload_all(client: httpx.Client, headers: dict[str, str]) -> dict[str, dict]:
    existing = client.get("/admin/company-documents", headers=headers, params={"limit": 200}).json()
    titles = {title for _, title, _ in DOCS.values()}
    by_title = {d["title"]: d for d in existing if d["title"] in titles}
    if "--reusar" in sys.argv and len(by_title) == len(DOCS):
        return {k: by_title[t] for k, (_, t, _) in DOCS.items()}
    for doc in existing:
        if doc["title"] in titles:
            client.delete(f"/admin/company-documents/{doc['id']}", headers=headers)
    ids: dict[str, str] = {}
    for key, (filename, title, _) in DOCS.items():
        response = client.post(
            "/admin/company-documents",
            headers=headers,
            files={"file": (filename, (CORPUS / filename).read_bytes(), "application/pdf")},
            data={"title": title, "visibility": "all", "all_databases": "true"},
        )
        response.raise_for_status()
        ids[key] = response.json()["id"]
    started = time.time()
    documents: dict[str, dict] = {}
    while time.time() - started < 600:
        documents = {
            k: client.get(f"/admin/company-documents/{i}", headers=headers).json()
            for k, i in ids.items()
        }
        if all(d["status"] not in ("pending", "processing") for d in documents.values()):
            break
        time.sleep(3)
    return documents


def ask(client: httpx.Client, headers: dict[str, str], question: str) -> dict:
    conversation = client.post("/conversations", json={}, headers=headers).json()["id"]
    text: list[str] = []
    tools: list[str] = []
    done: dict = {}
    error = None
    with client.stream(
        "POST",
        "/chat",
        json={"conversation_id": conversation, "action": "send", "message": question},
        headers=headers,
        timeout=300,
    ) as response:
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "text_delta":
                text.append(event["text"])
            elif kind == "tool_use":
                tools.append(event.get("name", ""))
            elif kind == "done":
                done = event
            elif kind == "error":
                error = event.get("message")
    # La respuesta se guarda en segundo plano al cerrar el stream: se espera
    # a que aparezca en vez de leerla en el mismo instante.
    assistant: dict = {}
    for _ in range(20):
        detail = client.get(f"/conversations/{conversation}", headers=headers).json()
        replies = [m for m in detail["messages"] if m["role"] == "assistant"]
        if replies:
            assistant = replies[-1]
            break
        time.sleep(0.5)
    return {
        "respuesta": "".join(text),
        "fuentes": [
            {"titulo": s["title"], "paginas": s.get("pages")}
            for s in assistant.get("sources") or []
        ],
        "herramientas": tools,
        "costo_usd": done.get("cost_usd") or 0.0,
        "error": error,
    }


def evaluate(question: tuple, answer: dict) -> dict:
    qid, key, _, expected = question
    text = answer["respuesta"]
    title = DOCS[key][1]
    cited = any(s["titulo"] == title for s in answer["fuentes"])
    no_access = any(p in norm(text) for p in NO_ACCESS)
    if expected == "negativa":
        # Decir que no lo encuentra o negarse por fuera de tema son seguros:
        # lo que falla es inventar.
        said_not_found = any(p in norm(text) for p in NOT_FOUND + OFF_TOPIC)
        invented_price = re.search(r"\$\s*\d|\d+\s*(usd|cop|pesos|dolares)", norm(text)) is not None
        ok = said_not_found and not invented_price and not no_access and not answer["error"]
        return {
            "ok": ok,
            "dato": said_not_found,
            "cita": None,
            "sin_acceso": no_access,
            "faltan": [],
        }
    missing = [group for group in expected if not any(has(text, alt) for alt in group)]
    # Una respuesta que deduce el dato ("parecería...") no lo encontró en el
    # documento: la primera corrida dio por buena una así (P12).
    hedged = any(p in norm(text) for p in HEDGES)
    ok = not missing and not hedged and cited and not no_access and not answer["error"]
    return {
        "ok": ok,
        "dato": not missing,
        "cita": cited,
        "sin_acceso": no_access,
        "faltan": missing,
    }


def main() -> None:
    download_corpus()
    with httpx.Client(base_url=API, timeout=120) as client:
        headers = login(client)
        provider = next(
            p for p in client.get("/admin/llm-providers", headers=headers).json() if p["is_active"]
        )
        reading = client.get("/admin/company-documents/ai-reading", headers=headers).json()
        print(
            f"Proveedor: {provider['provider']} · chat {provider['chat_model']} · lectura {reading['model']}"
        )
        documents = upload_all(client, headers)
        for key, doc in documents.items():
            print(
                f"  {key:10} {doc['status']:8} lectura={doc['reading_method']} "
                f"ia={doc['ai_page_count']}/{doc['page_count']} fragmentos={doc['chunk_count']} "
                f"costo={doc['ai_cost_usd']}"
            )
        results = []
        for question in QUESTIONS:
            answer = ask(client, headers, question[2])
            verdict = evaluate(question, answer)
            results.append(
                {
                    "id": question[0],
                    "documento": question[1],
                    "pregunta": question[2],
                    **answer,
                    **verdict,
                }
            )
            flag = "OK  " if verdict["ok"] else "FALLA"
            print(
                f"{flag} {question[0]} cita={verdict['cita']} dato={verdict['dato']} "
                f"sin_acceso={verdict['sin_acceso']} US${answer['costo_usd']:.5f} "
                + (f"faltan={verdict['faltan']} " if verdict["faltan"] else "")
                + "| "
                + answer["respuesta"].replace("\n", " ")[:140]
            )
        OUT.write_text(
            json.dumps(
                {"documentos": documents, "resultados": results}, ensure_ascii=False, indent=1
            ),
            encoding="utf-8",
        )
        passed = sum(r["ok"] for r in results)
        chat_cost = sum(r["costo_usd"] for r in results)
        read_cost = sum(d["ai_cost_usd"] or 0 for d in documents.values())
        print(
            f"\nRESULTADO {passed}/{len(results)} · lectura US${read_cost:.4f} · chat US${chat_cost:.4f}"
        )


if __name__ == "__main__":
    main()
