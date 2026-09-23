"""Batería con el conocimiento importado de sitios web reales de clientes.

Resultado y contexto: `docs/company_knowledge/prueba-sitios-clientes.md`.
Requiere haber corrido `prueba_sitios_clientes.py extraer` y `subir`.

Preguntas naturales sobre los tres sitios, cada una en el chat de la base
del cliente (el contenido de cada sitio quedó limitado a su base; el de SEO
Group, a todas), más casos difíciles:

- contenido de relleno del tema (FAQ en *lorem ipsum*) que no debe usarse;
- precios cuyo nombre de ruta es una imagen: no debe inventar la ruta;
- datos que el sitio contradice (teléfonos de compra);
- el sitio de un cliente no debe responder en el chat de otra base;
- un usuario no administrador consulta el conocimiento público.

    uv run python scripts/bateria_web_clientes.py

Gasta tokens del proveedor ACTIVO: con `gpt-6-luna`, ~US$0,02 por corrida.
"""

# ruff: noqa: E501

import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bateria_permisos_bases import API, NO_ACCESS, NOT_FOUND, Session, ask, norm

OUT = Path(tempfile.gettempdir()) / "savi-sitios-clientes"
SEO, SUR, FARM = "SEO Group", "Sur Andina", "Farmacias de Similares"


@dataclass
class Case:
    id: str
    sitio: str
    login: str  # CODIGO o CODIGO@BASE
    base: str
    pregunta: str
    esperado: list[list[str]] = field(default_factory=list)
    cita: str | None = None  # parte del título de la fuente citada
    prohibido: list[str] = field(default_factory=list)
    no_encontrado: bool = False
    extra: str | None = None


CASES = [
    # ── SEO Group (visible en todas las bases) ─────────────────────────────
    Case(
        "W01",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿cuánto cuesta el plan POS-20 de SEO?",
        [["800.000", "800,000", "800 000"]],
        "planes tarifarios POS",
    ),
    Case(
        "W02",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "qué incluye el plan R-B de recompra de folios y cuánto vale",
        [["411.300", "411,300"], ["720"]],
        "RECOMPRA DE FOLIOS",
    ),
    Case(
        "W03",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿dónde quedan las oficinas de SEO y a qué número llamo para soporte técnico?",
        [["calle 5"], ["311 531 0210", "3115310210", "316 559 2019", "3165592019"]],
        SEO,
    ),
    Case(
        "W04",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "desde qué año existe SEO ERP y de qué empresa es la marca",
        [["1991"], ["a&e", "a & e"]],
        # La página "Nosotros" no tiene h1: su título es el primer h2.
        "30 Años",
    ),
    Case(
        "W05",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "cuanto vale el paquete de recepcion electronica de 2000 transacciones",
        [["400.000", "400,000"]],
        "recepcion",
    ),
    Case(
        "W06",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿los productos de la tienda contienen gluten?",
        prohibido=["sportie", "juliette", "lorem"],
        extra="relleno",
    ),
    Case(
        "W07",
        SEO,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿SEO vende bicicletas de montaña?",
        prohibido=["trek", "domane"],
        no_encontrado=True,
    ),
    # Usuario no administrador, otra base: el conocimiento de SEO es de todos.
    Case(
        "W08",
        SEO,
        "QAINV@FRAMI",
        "FRAMI",
        "cuánto vale el plan POS de 50.000 folios",
        [["2.000.000", "2,000,000", "2 millones"]],
        "planes tarifarios POS",
    ),
    # ── Farmacias de Similares (solo su base) ──────────────────────────────
    Case(
        "F01",
        FARM,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿cuánto cuesta el amlodipino de 5 mg?",
        [["35"]],
        "AMLODIPINO",
    ),
    Case(
        "F02",
        FARM,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "tienen oseltamivir? a que precio",
        [["299"]],
        "OSELTAMIVIR",
    ),
    Case(
        "F03",
        FARM,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "qué geles o cremas tópicas para el dolor manejan",
        [["diclofenaco", "arnica", "árnica"]],
        FARM,
    ),
    Case(
        "F04",
        FARM,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "cuánto vale el suero hidratasim zero",
        [["25.50", "25,50", "25.5"]],
        FARM,
    ),
    Case(
        "F05",
        FARM,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿en qué moneda están los precios de la tienda en línea?",
        [["mxn", "peso mexicano", "pesos mexicanos"]],
        FARM,
    ),
    Case(
        "F06",
        FARM,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "¿venden llantas para carro?",
        prohibido=["$"],
        no_encontrado=True,
    ),
    # ── Sur Andina (solo su base) ──────────────────────────────────────────
    Case(
        "S01",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "cuántos despachos diarios hacen y a qué municipios van",
        [["60"], ["concordia"]],
        SUR,
    ),
    Case(
        "S02",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "¿cuántos kilos de equipaje puedo llevar sin pagar de más?",
        [["15"]],
        SUR,
    ),
    Case(
        "S03",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "con cuánto tiempo de anticipación tengo que llegar a la terminal",
        [["media hora", "30 minutos"]],
        SUR,
    ),
    Case(
        "S04",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "¿dónde queda la taquilla en Medellín?",
        [["terminal del sur"], ["4"]],
        SUR,
    ),
    Case(
        "S05",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "a qué hora sale el primer bus de Medellín para El Carmen de Atrato",
        [["5:30", "05:30", "5:45"]],
        SUR,
    ),
    Case(
        "S06",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "cuánto vale el pasaje de Medellín a Bolombolo",
        [["25,000", "25.000", "25 000"]],
        SUR,
    ),
    # El nombre de cada ruta en la tabla de tarifas es una imagen.
    Case(
        "S07",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "cuánto vale el pasaje de Medellín a Concordia",
        extra="no_inventa_ruta",
    ),
    # El sitio da dos juegos de teléfonos (tarifas vs. pie de página).
    Case(
        "S08",
        SUR,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "¿a qué número llamo para comprar tiquetes por teléfono?",
        [
            [
                "322-4754",
                "322 4754",
                "3224754",
                "361-3130",
                "361 3130",
                "314-797-1053",
                "314 797 1053",
            ]
        ],
        SUR,
    ),
    # ── Separación entre bases ─────────────────────────────────────────────
    Case(
        "X01",
        SUR,
        "SAVIQA",
        "FARMACIAS_SIMILARES",
        "cuántos kilos de equipaje puedo llevar sin pagar en el bus",
        prohibido=["15 kilos", "15 kg"],
        no_encontrado=True,
    ),
    Case(
        "X02",
        FARM,
        "SAVIQA@SUR_ANDINA",
        "SUR_ANDINA",
        "cuánto cuesta el oseltamivir de 75 mg",
        prohibido=["299"],
        no_encontrado=True,
    ),
]


def evaluate(case: Case, answer: dict) -> list[str]:
    text = norm(answer["respuesta"])
    problems: list[str] = []
    if answer["error"]:
        problems.append(f"error: {answer['error']}")
    if any(p in text for p in NO_ACCESS):
        problems.append("dijo 'no tengo acceso'")
    for group in case.esperado:
        if not any(norm(alt) in text for alt in group):
            problems.append(f"falta {group}")
    if case.cita and not any(norm(case.cita) in norm(source) for source in answer["fuentes"]):
        problems.append(f"no citó '{case.cita}'")
    for forbidden in case.prohibido:
        if norm(forbidden) in text:
            problems.append(f"dijo '{forbidden}'")
    if case.no_encontrado and not any(p in text for p in [*NOT_FOUND, "no veo", "no aparece"]):
        problems.append("no dijo que no lo encontró")
    if case.extra == "no_inventa_ruta":
        # Puede listar tarifas, pero no afirmar cuál es la de Concordia.
        affirms = re.search(r"concordia[^.\n]{0,60}\$\s?\d|\$\s?\d[^.\n]{0,40}concordia", text)
        hedges = any(
            p in text
            for p in NOT_FOUND
            + ["no se puede determinar", "no queda claro", "no identifica", "no aparece asociad"]
        )
        if affirms and not hedges:
            problems.append("afirmó una tarifa para Concordia que el sitio no asocia")
    return problems


def main() -> None:
    results = []
    with httpx.Client(base_url=API, timeout=120) as client:
        sessions: dict[str, Session] = {}
        bases = None
        for case in CASES:
            session = sessions.setdefault(case.login, Session(client, case.login))
            if bases is None:
                bases = {
                    b["code"]: b["id"]
                    for b in client.get("/erp-databases/available", headers=session.headers).json()
                }
            created = client.post(
                "/conversations",
                json={"erp_database_id": bases[case.base]},
                headers=session.headers,
            )
            created.raise_for_status()
            answer = ask(client, session, created.json()["id"], case.pregunta)
            problems = evaluate(case, answer)
            results.append({**case.__dict__, **answer, "problemas": problems})
            flag = "OK   " if not problems else "FALLA"
            print(
                f"{flag} {case.id} {case.base[:10]:10} "
                + (f"{problems} " if problems else "")
                + "| "
                + answer["respuesta"].replace("\n", " ")[:150]
            )
    out = OUT / "resultado-preguntas.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for sitio in (SEO, FARM, SUR):
        rows = [r for r in results if r["sitio"] == sitio and not r["id"].startswith("X")]
        print(f"  {sitio:24} {sum(not r['problemas'] for r in rows)}/{len(rows)}")
    rows = [r for r in results if r["id"].startswith("X")]
    print(f"  {'Separación entre bases':24} {sum(not r['problemas'] for r in rows)}/{len(rows)}")
    passed = sum(not r["problemas"] for r in results)
    cost = sum(r["costo_usd"] for r in results)
    print(f"\nRESULTADO {passed}/{len(results)} · chat US${cost:.4f} · detalle en {out}")


if __name__ == "__main__":
    main()
