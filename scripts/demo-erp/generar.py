"""Base de demo del ERP con una empresa inventada: Rodamundo Llantas S.A.S.

Sirve para mostrar SAVI en internet sin datos de ningún cliente. Toma de una
base del ERP solo dos cosas:

- la **estructura** (`pg_dump --schema-only`): tablas, vistas y funciones;
- los **catálogos que no son del cliente**: países, departamentos y municipios
  (DANE), tarifas de IVA, líneas de impuesto y los formularios del ERP, que
  son de SEO.

Todo lo demás se genera con una semilla fija, así que dos corridas dan la
misma base: la empresa, sus almacenes, productos, terceros, 24 meses de
ventas y compras, los saldos de inventario de cada mes, la cartera y los
usuarios de la demo.

Uso (desde la raíz del monorepo, con el entorno del backend):

    PGHOST=localhost PGPORT=5433 PGUSER=postgres PGPASSWORD=... \\
    uv run --project backend python scripts/demo-erp/generar.py \\
        --source imporllantas --target savi_demo_erp \\
        --pg-bin "C:/Program Files/PostgreSQL/16/bin" --replace

La conexión sale de las variables estándar de libpq (`PGHOST`, `PGPORT`,
`PGUSER`, `PGPASSWORD`). Ver `scripts/demo-erp/README.md`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import os
import random
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import asyncpg

SEED = 20261118
TODAY = date(2026, 11, 18)
MONTHS = 24  # de diciembre de 2024 a noviembre de 2026
FIRST_MONTH = date(2024, 12, 1)

# El nombre de la base destino tiene que decir "demo": así `--replace` nunca
# puede borrar la base de un cliente por un error de tipeo.
_SAFE_TARGET = re.compile(r"^[a-z0-9_]*demo[a-z0-9_]*$")

# Catálogos que se copian tal cual desde la base de origen. No tienen datos de
# la empresa: son del DANE, de la DIAN (IVA y retenciones) o del propio ERP.
COPIED_TABLES: list[tuple[str, str]] = [
    ("General", "Pais"),
    ("General", "Departamento"),
    ("General", "Municipio"),
    ("Inventario", "IndicadorIva"),
    ("Inventario", "IndicadorRetencion"),
    ("General", "Linea"),
    ("Seguridad", "Formulario"),
    ("Seguridad", "Accion"),
]

DEMO_PASSWORD = "Demo2026"

IVA = Decimal("19")
CENT = Decimal("1")


def money(value: Decimal | float | int) -> Decimal:
    """Pesos sin centavos, como factura el ERP."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def nit_dv(nit: str) -> int:
    """Dígito de verificación de la DIAN."""
    weights = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    total = sum(int(d) * weights[i] for i, d in enumerate(reversed(nit)))
    rest = total % 11
    return rest if rest < 2 else 11 - rest


# ---------------------------------------------------------------------------
# Datos de referencia inventados
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Andrés",
    "Carolina",
    "Juan",
    "María",
    "Luis",
    "Paola",
    "Carlos",
    "Diana",
    "Jorge",
    "Natalia",
    "Felipe",
    "Laura",
    "Santiago",
    "Valentina",
    "Camilo",
    "Daniela",
    "Javier",
    "Lina",
    "Sergio",
    "Angélica",
    "Mauricio",
    "Juliana",
    "Óscar",
    "Catalina",
    "Hernán",
    "Marcela",
    "Ricardo",
    "Alejandra",
    "Fabián",
    "Sandra",
    "Esteban",
    "Viviana",
    "Gustavo",
    "Lorena",
    "Iván",
    "Mónica",
    "Wilson",
    "Patricia",
    "Édgar",
    "Claudia",
]
LAST_NAMES = [
    "Gómez",
    "Rodríguez",
    "Martínez",
    "López",
    "García",
    "Hernández",
    "Ramírez",
    "Torres",
    "Vargas",
    "Castro",
    "Rojas",
    "Moreno",
    "Jiménez",
    "Muñoz",
    "Díaz",
    "Ortiz",
    "Suárez",
    "Restrepo",
    "Cárdenas",
    "Ospina",
    "Salazar",
    "Quintero",
    "Valencia",
    "Arango",
    "Londoño",
    "Montoya",
    "Zapata",
    "Cardona",
    "Henao",
    "Giraldo",
    "Franco",
    "Rincón",
]
COMPANY_FIRST = [
    "Transportes",
    "Logística",
    "Distribuidora",
    "Servicios",
    "Comercializadora",
    "Taxis",
    "Expreso",
    "Inversiones",
    "Agroindustrial",
    "Constructora",
    "Mensajería",
]
COMPANY_SECOND = [
    "La Ruta",
    "El Cafetal",
    "Andina",
    "del Eje",
    "Los Nevados",
    "Sol de Oriente",
    "Bahía",
    "Montaña Verde",
    "El Puente",
    "Río Claro",
    "La Pradera",
    "Altavista",
    "Cordillera",
    "Santa Lucía",
    "El Roble",
    "Horizonte",
    "Palmar",
    "Las Acacias",
]
COMPANY_SUFFIX = ["S.A.S.", "Ltda.", "S.A.S.", "S.A.", "S.A.S."]
STREETS = ["Calle", "Carrera", "Avenida", "Diagonal", "Transversal"]

PREMIUM = ["MICHELIN", "BRIDGESTONE", "PIRELLI", "CONTINENTAL", "GOODYEAR"]
MIDRANGE = ["HANKOOK", "KUMHO", "YOKOHAMA", "GENERAL TIRE", "FIRESTONE"]
ECONOMY = ["RODAX", "VIATRA", "KORDO"]  # marcas inventadas
TREADS = {
    "AUTOMOVIL": ["RUTA", "CONFORT", "SPORT", "ECO"],
    "CAMIONETA": ["HT", "AT", "MT", "TOURING"],
    "CAMION": ["DIRECCIONAL", "TRACCION", "MIXTA"],
}
SIZES = {
    "AUTOMOVIL": [
        ("175/70R13", 13),
        ("185/60R14", 14),
        ("185/65R14", 14),
        ("195/55R15", 15),
        ("195/65R15", 15),
        ("205/55R16", 16),
        ("205/60R16", 16),
        ("215/55R17", 17),
        ("225/45R17", 17),
        ("225/45R18", 18),
    ],
    "CAMIONETA": [
        ("215/65R16", 16),
        ("235/75R15", 15),
        ("245/70R16", 16),
        ("265/70R16", 16),
        ("265/65R17", 17),
        ("255/55R18", 18),
    ],
    "CAMION": [("11R22.5", 22), ("295/80R22.5", 22), ("215/75R17.5", 17)],
}
RIM_PRICE = {
    13: 175_000,
    14: 225_000,
    15: 290_000,
    16: 390_000,
    17: 520_000,
    18: 650_000,
    22: 1_450_000,
}
TIER = {
    **dict.fromkeys(PREMIUM, 1.28),
    **dict.fromkeys(MIDRANGE, 1.0),
    **dict.fromkeys(ECONOMY, 0.74),
}

SERVICES = [
    ("SRV-001", "ALINEACION", 45_000),
    ("SRV-002", "BALANCEO POR LLANTA", 12_000),
    ("SRV-003", "MONTAJE POR LLANTA", 10_000),
    ("SRV-004", "ROTACION DE LLANTAS", 25_000),
    ("SRV-005", "REPARACION DE PINCHAZO", 15_000),
    ("SRV-006", "VALVULA NITROGENO", 8_000),
]
ACCESSORIES = [
    ("ACC-001", "VALVULA METALICA", 9_000),
    ("ACC-002", "KIT TUERCAS DE SEGURIDAD", 85_000),
    ("ACC-003", "SENSOR DE PRESION TPMS", 160_000),
    ("ACC-004", "COMPRESOR PORTATIL 12V", 140_000),
    ("ACC-005", "MEDIDOR DE PRESION DIGITAL", 38_000),
    ("ACC-006", "PARCHE RADIAL X10", 32_000),
]
BATTERIES = [
    ("BAT-001", "BATERIA 42 MF", 390_000),
    ("BAT-002", "BATERIA 24 MF", 470_000),
    ("BAT-003", "BATERIA 34 MF", 520_000),
    ("BAT-004", "BATERIA 27 MF", 610_000),
    ("BAT-005", "BATERIA 4D CAMION", 1_250_000),
]
RIMS = [
    (f"RIN-{i + 1:03d}", f"RIN {size} ALUMINIO {style}", price)
    for i, (size, style, price) in enumerate(
        [
            (14, "5 RAYOS", 380_000),
            (15, "MULTIRRAYO", 450_000),
            (16, "DEPORTIVO", 560_000),
            (17, "6 RAYOS", 690_000),
            (18, "BICOLOR", 820_000),
            (15, "ACERO", 190_000),
            (16, "ACERO", 230_000),
        ]
    )
]

GROUPS = [
    (1, "01", "LLANTAS AUTOMOVIL"),
    (2, "02", "LLANTAS CAMIONETA"),
    (3, "03", "LLANTAS CAMION"),
    (4, "04", "RINES"),
    (5, "05", "BATERIAS"),
    (6, "06", "ACCESORIOS"),
    (7, "07", "SERVICIOS"),
]
SELLERS = [
    ("Mateo", "Cifuentes"),
    ("Adriana", "Bermúdez"),
    ("Julián", "Arbeláez"),
    ("Tatiana", "Echeverri"),
    ("Nicolás", "Villegas"),
    ("Manuela", "Duque"),
]
SELLER_WEIGHTS = [0.27, 0.22, 0.18, 0.15, 0.11, 0.07]
SUPPLIERS = [
    ("Importadora Rueda Firme S.A.S.", ["MICHELIN", "BFGOODRICH"]),
    ("Distribuciones Andes Llantas S.A.S.", ["BRIDGESTONE", "FIRESTONE"]),
    ("Pirelli Partners Colombia S.A.S.", ["PIRELLI"]),
    ("Continental Rutas S.A.S.", ["CONTINENTAL", "GENERAL TIRE"]),
    ("Goodyear Mayoristas del Centro S.A.S.", ["GOODYEAR"]),
    ("Asia Tire Import S.A.S.", ["HANKOOK", "KUMHO", "YOKOHAMA"]),
    ("Llantas Económicas del Pacífico S.A.S.", ["RODAX", "VIATRA", "KORDO"]),
    ("Rines y Accesorios Premium Ltda.", ["RINES", "ACCESORIOS"]),
    ("Energía Automotriz S.A.S.", ["BATERIAS"]),
]

# Patrón de un año: diciembre y mitad de año son temporada de viajes.
SEASON = {
    1: 0.86,
    2: 0.88,
    3: 0.97,
    4: 0.95,
    5: 1.0,
    6: 1.12,
    7: 1.08,
    8: 1.0,
    9: 0.96,
    10: 1.0,
    11: 1.05,
    12: 1.34,
}


# ---------------------------------------------------------------------------
# Modelo en memoria
# ---------------------------------------------------------------------------


@dataclass
class Product:
    id: int
    code: str
    description: str
    group_id: int
    is_service: bool
    price: Decimal  # precio de venta antes de IVA
    cost: Decimal
    weight: float  # popularidad relativa
    stops_selling: date | None = None  # desde esa fecha nadie lo compra
    supplier_key: str = ""


@dataclass
class Third:
    id: int
    kind: str  # person | company | final | seller | supplier | buyer
    credit_days: int = 0
    late_payer: bool = False
    brands: list[str] = field(default_factory=list)


@dataclass
class Stock:
    qty: int = 0
    avg_cost: Decimal = Decimal(0)
    month_in: int = 0
    month_out: int = 0
    month_start: int = 0


class Demo:
    def __init__(self, municipios: dict[str, int]) -> None:
        self.rng = random.Random(SEED)
        self.municipios = municipios
        self.rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.products: list[Product] = []
        self.thirds: list[Third] = []
        self.next_third = 1

    # -- utilidades -----------------------------------------------------
    def add(self, schema: str, table: str, **row: Any) -> None:
        self.rows[(schema, table)].append(row)

    def phone(self) -> str:
        return f"300555{self.rng.randint(1000, 9999)}"

    def landline(self) -> str:
        return f"606555{self.rng.randint(1000, 9999)}"

    def address(self) -> str:
        return (
            f"{self.rng.choice(STREETS)} {self.rng.randint(1, 120)} "
            f"# {self.rng.randint(1, 90)}-{self.rng.randint(1, 99)}"
        )

    def city(self) -> int:
        # Eje cafetero y alrededores; la mitad en la sede.
        pool = ["66001", "66001", "66170", "17001", "63001", "76111", "66682"]
        return self.municipios.get(self.rng.choice(pool), self.municipios["66001"])

    @staticmethod
    def slug(text: str) -> str:
        table = str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")
        return re.sub(r"[^a-z0-9]+", ".", text.translate(table).lower()).strip(".")

    # -- empresa --------------------------------------------------------
    def company(self, logo: bytes) -> None:
        nit = "901555010"
        self.add(
            "Empresa",
            "Empresa",
            idEmpresa=1,
            nit=nit,
            digitoVerificacion=str(nit_dv(nit)),
            razonSocial="RODAMUNDO LLANTAS S.A.S.",
            idMunicipio=self.municipios["66001"],
            direccion="Avenida 30 de Agosto # 45-120",
            telefono="6065550100",
            celular="3005550100",
            email="contacto@example.com",
            representanteLegal="ELENA MARQUEZ RIVAS",
            cargo="GERENTE GENERAL",
            logo=logo,
        )
        self.add(
            "Empresa",
            "CentroCosto",
            idCentroCosto=1,
            idEmpresa=1,
            codigo="01",
            descripcion="SEDE PEREIRA",
            direccion="Avenida 30 de Agosto # 45-120",
            telefono="6065550100",
        )
        self.add(
            "Inventario",
            "Almacen",
            idAlmacen=1,
            codigo="01",
            descripcion="BODEGA PRINCIPAL",
            idCentroCosto=1,
        )
        self.add(
            "Inventario",
            "Almacen",
            idAlmacen=2,
            codigo="02",
            descripcion="PUNTO DE VENTA DOSQUEBRADAS",
            idCentroCosto=1,
        )
        self.add(
            "SEO",
            "Modulo",
            idModulo=1,
            activoFijo=False,
            cuentaPagar=True,
            cuentaCobrar=True,
            contabilidad=True,
            nomina=False,
            mantenimiento=False,
            cultivo=False,
            carteraFinanciera=False,
            inventario=True,
            produccionAvicola=False,
            bombero=False,
            controlPrestamo=False,
            herramienta=False,
            presupuesto=False,
        )
        for doc_id, code, description, movement in [
            (3, "FV", "FACTURA ELECTRONICA DE VENTA", 1),
            (5, "FP", "FACTURA PROVEEDOR", 0),
        ]:
            self.add(
                "General",
                "Documento",
                idDocumento=doc_id,
                codigo=code,
                descripcion=description,
                tipoMovimiento=movement,
                formaPago=0,
                numeracionAutomatica=True,
                idCentroCosto=1,
            )

    # -- terceros -------------------------------------------------------
    def _third(self, kind: str, **values: Any) -> Third:
        third = Third(self.next_third, kind)
        self.next_third += 1
        self.thirds.append(third)
        base: dict[str, Any] = dict(  # noqa: C408 (mismos nombres que las columnas)
            idTercero=third.id,
            nombreComercial="",
            segundoNombre="",
            segundoApellido="",
            representanteLegal="",
            direccion=self.address(),
            telefonoFijo=self.landline(),
            celular=self.phone(),
            idMunicipio=self.city(),
            estado=True,
            bloqueoTercero=False,
            terceroVip=False,
            cliente=False,
            proveedor=False,
            empleado=False,
            diasCredito=0,
            cupoCredito=Decimal(0),
            fechaIngreso=datetime(2023, 1, 15, tzinfo=UTC)
            + timedelta(days=self.rng.randint(0, 600)),
        )
        base.update(values)
        base["nombreCompleto"] = base["razonSocial"].strip() or " ".join(
            p for p in (base["primerNombre"], base["primerApellido"]) if p
        )
        self.add("Tercero", "Tercero", **base)
        return third

    def _person(
        self, kind: str, first: str, last: str, second_last: str = "", **values: Any
    ) -> Third:
        number = str(self.rng.randint(10_000_000, 1_199_999_999))
        email = f"{self.slug(first)}.{self.slug(last)}{self.rng.randint(1, 99)}@example.com"
        return self._third(
            kind,
            numeroIdentificacion=number,
            tipoDocumento=0,
            razonSocial="",
            primerNombre=first.upper(),
            primerApellido=last.upper(),
            segundoApellido=second_last.upper(),
            digitoVerificacion=0,
            email=email,
            **values,
        )

    def _company(self, kind: str, name: str, **values: Any) -> Third:
        nit = str(self.rng.randint(800_000_000, 901_999_999))
        email = f"compras@{self.slug(name).split('.')[0]}{self.rng.randint(1, 99)}.example.com"
        return self._third(
            kind,
            numeroIdentificacion=nit,
            tipoDocumento=3,
            razonSocial=name.upper(),
            primerNombre="",
            primerApellido="",
            digitoVerificacion=nit_dv(nit),
            email=email,
            **values,
        )

    def thirds_all(self) -> None:
        final = self._third(
            "final",
            numeroIdentificacion="222222222222",
            tipoDocumento=0,
            razonSocial="CONSUMIDOR FINAL",
            primerNombre="",
            primerApellido="",
            digitoVerificacion=0,
            email="",
            cliente=True,
            telefonoFijo="",
            celular="",
        )
        self.final = final
        for first, last in SELLERS:
            self._person("seller", first, last, empleado=True)
        self.buyer = self._person("buyer", "Rocío", "Palacios", empleado=True)
        for name, brands in SUPPLIERS:
            supplier = self._company("supplier", name, proveedor=True, diasCredito=60)
            supplier.brands = brands
        for _ in range(330):
            credit = 30 if self.rng.random() < 0.12 else 0
            third = self._person(
                "person",
                self.rng.choice(FIRST_NAMES),
                self.rng.choice(LAST_NAMES),
                self.rng.choice(LAST_NAMES),
                cliente=True,
                diasCredito=credit,
                cupoCredito=Decimal(3_000_000 if credit else 0),
            )
            third.credit_days = credit
        seen: set[str] = set()
        while len(seen) < 120:
            name = (
                f"{self.rng.choice(COMPANY_FIRST)} {self.rng.choice(COMPANY_SECOND)} "
                f"{self.rng.choice(COMPANY_SUFFIX)}"
            )
            if name in seen:
                continue
            seen.add(name)
            credit = self.rng.choice([0, 30, 30, 60, 60, 90]) if self.rng.random() < 0.8 else 0
            third = self._company(
                "company",
                name,
                cliente=True,
                diasCredito=credit,
                representanteLegal=(
                    f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
                ).upper(),
                cupoCredito=Decimal(self.rng.choice([10, 20, 40, 80]) * 1_000_000 if credit else 0),
            )
            third.credit_days = credit
            third.late_payer = credit > 0 and self.rng.random() < 0.12

    # -- productos ------------------------------------------------------
    def catalog(self) -> None:
        for group_id, code, description in GROUPS:
            self.add("Inventario", "Grupo", idGrupo=group_id, codigo=code, descripcion=description)
        next_id = 1
        group_of = {"AUTOMOVIL": 1, "CAMIONETA": 2, "CAMION": 3}
        brands = PREMIUM + MIDRANGE + ECONOMY
        for segment, sizes in SIZES.items():
            for size, rim in sizes:
                for brand in self.rng.sample(brands, k=7 if segment != "CAMION" else 5):
                    tread = self.rng.choice(TREADS[segment])
                    price = RIM_PRICE[rim] * TIER[brand] * self.rng.uniform(0.92, 1.08)
                    price *= {"AUTOMOVIL": 1.0, "CAMIONETA": 1.15, "CAMION": 1.0}[segment]
                    popularity = self.rng.paretovariate(1.6) * (1.6 if rim in (14, 15, 16) else 1)
                    self.products.append(
                        Product(
                            next_id,
                            f"LL{next_id:05d}",
                            f"LLANTA {size} {brand} {tread}",
                            group_of[segment],
                            False,
                            money(price / 1000) * 1000,
                            money(price * self.rng.uniform(0.66, 0.74) / 100) * 100,
                            popularity,
                            supplier_key=brand,
                        )
                    )
                    next_id += 1
        for items, group_id, key in [
            (RIMS, 4, "RINES"),
            (BATTERIES, 5, "BATERIAS"),
            (ACCESSORIES, 6, "ACCESORIOS"),
        ]:
            for code, description, price in items:
                self.products.append(
                    Product(
                        next_id,
                        code,
                        description,
                        group_id,
                        False,
                        Decimal(price),
                        money(price * self.rng.uniform(0.6, 0.7) / 100) * 100,
                        self.rng.uniform(0.3, 1.5),
                        supplier_key=key,
                    )
                )
                next_id += 1
        for code, description, price in SERVICES:
            self.products.append(
                Product(next_id, code, description, 7, True, Decimal(price), Decimal(0), 0.0)
            )
            next_id += 1
        # Una parte del inventario deja de rotar: lo que SAVI muestra como
        # "productos sin movimiento".
        goods = [p for p in self.products if not p.is_service]
        for product in self.rng.sample(goods, k=len(goods) // 9):
            product.stops_selling = FIRST_MONTH + timedelta(days=self.rng.randint(20, 330))
        for product in self.products:
            self.add(
                "Inventario",
                "Producto",
                idProducto=product.id,
                codigo=product.code,
                descripcion=product.description,
                tipo=1 if product.is_service else 0,
                idGrupo=product.group_id,
                idLinea=6 if product.is_service else 2,
                solicitaLotes=False,
                indicador=0,
                referencia=product.code,
                idIndicadorRetencion=1,
                nombreComercial="",
                valorCosto=product.cost,
                valorVenta=product.price,
                estado=True,
                fueraCatalogo=False,
            )

    # -- movimientos ----------------------------------------------------
    def movements(self) -> None:
        rng = self.rng
        goods = [p for p in self.products if not p.is_service]
        services = {p.code: p for p in self.products if p.is_service}
        sellers = [t for t in self.thirds if t.kind == "seller"]
        persons = [t for t in self.thirds if t.kind == "person"]
        companies = [t for t in self.thirds if t.kind == "company"]
        suppliers = [t for t in self.thirds if t.kind == "supplier"]
        supplier_of = {b: s for s in suppliers for b in s.brands}
        for p in goods:
            if p.supplier_key not in supplier_of:
                supplier_of[p.supplier_key] = suppliers[0]
        stock: dict[tuple[int, int], Stock] = {(p.id, a): Stock() for p in goods for a in (1, 2)}
        invoice_id = purchase_id = detail_id = pdetail_id = cartera_id = saldo_id = 1
        invoice_number, purchase_number = 10_001, 5_001

        def buy(when: datetime, lines: list[tuple[Product, int, int]]) -> None:
            nonlocal purchase_id, pdetail_id, purchase_number, cartera_id
            if not lines:
                return
            supplier = supplier_of[lines[0][0].supplier_key]
            subtotal = Decimal(0)
            for n, (product, almacen, qty) in enumerate(lines, start=1):
                unit = money(product.cost * Decimal(str(rng.uniform(0.97, 1.03))))
                line = unit * qty
                vat = money(line * IVA / 100)
                self.add(
                    "CuentaPagar",
                    "DetalleFacturaCompra",
                    idDetalleFacturaCompra=pdetail_id,
                    idFacturaCompra=purchase_id,
                    numeroLinea=n,
                    idProducto=product.id,
                    idAlmacen=almacen,
                    porcentajeDescuento=Decimal(0),
                    cantidad=qty,
                    valorUnitario=unit,
                    subtotal=line,
                    valorDescuento=Decimal(0),
                    idIndicadorIva=2,
                    porcentajeIva=IVA,
                    valorIva=vat,
                    valorGravadoIva=line,
                    valorExentoIva=Decimal(0),
                    valorExcluidoIva=Decimal(0),
                    total=line + vat,
                    fechaCreacion=when,
                    fechaModificacion=when,
                )
                pdetail_id += 1
                subtotal += line
                s = stock[(product.id, almacen)]
                total_cost = s.avg_cost * s.qty + unit * qty
                s.qty += qty
                s.month_in += qty
                s.avg_cost = money(total_cost / s.qty) if s.qty else unit
            vat = money(subtotal * IVA / 100)
            retention = money(subtotal * Decimal("0.025"))
            total = subtotal + vat - retention
            due = when + timedelta(days=60)
            self.add(
                "CuentaPagar",
                "FacturaCompra",
                idFacturaCompra=purchase_id,
                idDocumento=5,
                numero=purchase_number,
                referenciaFacturaProveedor=f"FE{rng.randint(10000, 99999)}",
                idCentroCosto=1,
                fecha=when,
                fechaVencimiento=due,
                idTercero=supplier.id,
                idTerceroEmpleado=self.buyer.id,
                diasCredito=60,
                numeroCuotas=1,
                subtotal=subtotal,
                descuento=Decimal(0),
                valorGravadoIva=subtotal,
                valorExentoIva=Decimal(0),
                valorExcluidoIva=Decimal(0),
                valorIva=vat,
                valorImpuestosRetencion=retention,
                total=total,
                anulada=False,
                fechaCreacion=when,
                fechaModificacion=when,
                idUsuarioCreacion=1,
                idUsuarioModificacion=1,
            )
            paid = total if due.date() < TODAY - timedelta(days=rng.randint(0, 25)) else Decimal(0)
            self.add(
                "Cartera",
                "FacturaTercero",
                idFacturaTercero=cartera_id,
                idDocumento=5,
                numero=purchase_number,
                cuota=1,
                idTercero=supplier.id,
                idCentroCosto=1,
                fechaFactura=when,
                fechaVencimientoCuota=due,
                valorDocumento=total,
                valorPagado=paid,
                valorSaldo=total - paid,
                tipoDocumento=3,
                idFacturaCompra=purchase_id,
                fechaCreacion=when,
                fechaModificacion=when,
            )
            cartera_id += 1
            purchase_id += 1
            purchase_number += 1

        def at(day: date, hour_from: int = 8) -> datetime:
            return datetime(
                day.year,
                day.month,
                day.day,
                rng.randint(hour_from, 17),
                rng.randint(0, 59),
                rng.randint(0, 59),
                tzinfo=UTC,
            )

        for month_index in range(MONTHS):
            month = date(
                FIRST_MONTH.year + (FIRST_MONTH.month - 1 + month_index) // 12,
                (FIRST_MONTH.month - 1 + month_index) % 12 + 1,
                1,
            )
            next_month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
            last_day = min(next_month - timedelta(days=1), TODAY - timedelta(days=1))
            for s in stock.values():
                s.month_start = s.qty
                s.month_in = s.month_out = 0
            if month_index == 0:
                # Inventario inicial: una compra por proveedor el primer día.
                by_supplier: dict[int, list[tuple[Product, int, int]]] = defaultdict(list)
                for p in goods:
                    base = max(4, int(p.weight * 10))
                    by_supplier[supplier_of[p.supplier_key].id].append((p, 1, base))
                    by_supplier[supplier_of[p.supplier_key].id].append((p, 2, max(2, base // 3)))
                for lines in by_supplier.values():
                    for chunk in range(0, len(lines), 40):
                        buy(at(month + timedelta(days=1)), lines[chunk : chunk + 40])
            else:
                # Reposición a comienzo de mes: lo que bajó del mínimo vuelve al máximo.
                orders: dict[int, list[tuple[Product, int, int]]] = defaultdict(list)
                for p in goods:
                    if p.stops_selling and p.stops_selling < month:
                        continue
                    for almacen in (1, 2):
                        target = max(4, int(p.weight * (10 if almacen == 1 else 4)))
                        s = stock[(p.id, almacen)]
                        if s.qty < target // 2:
                            orders[supplier_of[p.supplier_key].id].append(
                                (p, almacen, target - s.qty)
                            )
                for lines in orders.values():
                    for chunk in range(0, len(lines), 40):
                        buy(
                            at(month + timedelta(days=rng.randint(0, 4))), lines[chunk : chunk + 40]
                        )
            price_factor = Decimal("1.06") if month >= date(2026, 1, 1) else Decimal(1)
            invoices = int(205 * SEASON[month.month] * (1 + 0.012 * month_index))
            days = (last_day - month).days + 1
            if days <= 0:
                continue
            invoices = int(invoices * days / ((next_month - month).days))
            for _ in range(invoices):
                day = month + timedelta(days=rng.randrange(days))
                when = at(day)
                roll = rng.random()
                customer = (
                    self.final
                    if roll < 0.28
                    else rng.choice(persons)
                    if roll < 0.74
                    else rng.choice(companies)
                )
                seller = rng.choices(sellers, weights=SELLER_WEIGHTS)[0]
                almacen = 1 if rng.random() < 0.68 else 2
                n_lines = rng.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
                sale: list[tuple[Product, int, Decimal, Decimal]] = []
                available = [p for p in goods if not (p.stops_selling and p.stops_selling <= day)]
                for product in rng.choices(
                    available, weights=[p.weight for p in available], k=n_lines
                ):
                    s = stock[(product.id, almacen)]
                    wanted = rng.choices([1, 2, 4], weights=[0.25, 0.35, 0.4])[0]
                    if customer.kind == "company":
                        wanted = rng.choice([2, 4, 4, 6, 8])
                    qty = min(wanted, s.qty)
                    if qty <= 0 or any(line[0] is product for line in sale):
                        continue
                    unit = money(product.price * price_factor)
                    sale.append((product, qty, unit, s.avg_cost))
                    s.qty -= qty
                    s.month_out += qty
                if not sale:
                    continue
                tires = sum(q for p, q, _, _ in sale if p.group_id in (1, 2, 3))
                if tires and rng.random() < 0.45:
                    sale.append((services["SRV-001"], 1, services["SRV-001"].price, Decimal(0)))
                if tires and rng.random() < 0.6:
                    srv = services["SRV-002"]
                    sale.append((srv, tires, srv.price, Decimal(0)))
                discount_pct = (
                    Decimal(rng.choice([0, 0, 3, 5, 8]))
                    if customer.kind == "company"
                    else Decimal(0)
                )
                subtotal = discount_total = vat_total = Decimal(0)
                for n, (product, qty, unit, cost) in enumerate(sale, start=1):
                    gross = unit * qty
                    discount = money(gross * discount_pct / 100)
                    line = gross - discount
                    vat = money(line * IVA / 100)
                    self.add(
                        "CuentaCobrar",
                        "DetalleFactura",
                        idDetalleFactura=detail_id,
                        idFactura=invoice_id,
                        numeroLinea=n,
                        idProducto=product.id,
                        idAlmacen=almacen,
                        porcentajeDescuento=discount_pct,
                        cantidad=qty,
                        costo=cost,
                        valorUnitario=unit,
                        total=line,
                        valorDescuento=discount,
                        idIndicadorIva=2,
                        porcentajeIva=IVA,
                        valorIva=vat,
                        totalGravadoIva=line,
                        descripcionProducto=product.description,
                        fechaCreacion=when,
                        fechaModificacion=when,
                    )
                    detail_id += 1
                    subtotal += line
                    discount_total += discount
                    vat_total += vat
                credit = customer.credit_days if customer.kind in ("company", "person") else 0
                if credit and rng.random() < 0.25:
                    credit = 0  # también pagan de contado a veces
                total = subtotal + vat_total
                due = when + timedelta(days=credit)
                voided = rng.random() < 0.003
                self.add(
                    "CuentaCobrar",
                    "Factura",
                    idFactura=invoice_id,
                    idDocumento=3,
                    numero=invoice_number,
                    idCentroCosto=1,
                    fecha=when,
                    fechaVencimiento=due,
                    idTercero=customer.id,
                    idTerceroEmpleado=seller.id,
                    diasCredito=credit,
                    numeroCuotas=1 if credit else 0,
                    valorPagoEfectivo=Decimal(0) if credit else total,
                    subtotal=subtotal + discount_total,
                    descuento=discount_total,
                    valorGravadoIva=subtotal,
                    valorExentoIva=Decimal(0),
                    valorExcluidoIva=Decimal(0),
                    valorImpuestosRetencion=Decimal(0),
                    valorImpuestoIva=vat_total,
                    total=total,
                    anulada=voided,
                    fechaCreacion=when,
                    fechaModificacion=when,
                    idUsuarioCreacion=1,
                    idUsuarioModificacion=1,
                )
                if credit and not voided:
                    overdue_days = (TODAY - due.date()).days
                    if customer.late_payer and overdue_days > 0:
                        paid = money(total * Decimal(str(rng.choice([0, 0, 0.3, 0.5]))))
                    elif overdue_days > rng.randint(-10, 20):
                        paid = total
                    else:
                        paid = Decimal(0)
                    self.add(
                        "Cartera",
                        "FacturaTercero",
                        idFacturaTercero=cartera_id,
                        idDocumento=3,
                        numero=invoice_number,
                        cuota=1,
                        idTercero=customer.id,
                        idCentroCosto=1,
                        fechaFactura=when,
                        fechaVencimientoCuota=due,
                        valorDocumento=total,
                        valorPagado=paid,
                        valorSaldo=total - paid,
                        tipoDocumento=2,
                        idFactura=invoice_id,
                        idTerceroEmpleado=seller.id,
                        fechaCreacion=when,
                        fechaModificacion=when,
                    )
                    cartera_id += 1
                invoice_id += 1
                invoice_number += 1
            stamp = datetime(last_day.year, last_day.month, last_day.day, 23, 0, tzinfo=UTC)
            for (product_id, almacen), s in stock.items():
                product = self.products[product_id - 1]
                self.add(
                    "Inventario",
                    "SaldoInventario",
                    idSaldoInventario=saldo_id,
                    idAlmacen=almacen,
                    idProducto=product_id,
                    anio=month.year,
                    mes=month.month,
                    cantidadInicial=Decimal(s.month_start),
                    cantidadEntrada=Decimal(s.month_in),
                    cantidadSalida=Decimal(s.month_out),
                    cantidadComprometida=Decimal(0),
                    cantidadActual=Decimal(s.qty),
                    costoPromedio=s.avg_cost or product.cost,
                    cantidadMinima=Decimal(max(2, int(product.weight * 3))),
                    cantidadMaxima=Decimal(max(6, int(product.weight * 12))),
                    fechaCreacion=stamp,
                    fechaModificacion=stamp,
                )
                saldo_id += 1

    # -- usuarios -------------------------------------------------------
    def users(self, forms: list[tuple[int, str]]) -> list[tuple[str, str, str]]:
        clave = hashlib.md5(DEMO_PASSWORD.encode("utf-8")).hexdigest()
        profiles = [
            ("DEMO", "ADMINISTRADOR DEMO", True, None),
            (
                "GERENTE",
                "GERENCIA COMERCIAL",
                False,
                {"CUENTACOBRAR", "CUENTAPAGAR", "INVENTARIO", "CARTERA", "TERCERO", "VENTA"},
            ),
            ("VENDEDOR", "ASESOR DE VENTAS", False, {"CUENTACOBRAR", "INVENTARIO", "VENTA"}),
        ]
        permiso = 1
        summary = []
        for user_id, (code, name, admin, modules) in enumerate(profiles, start=1):
            self.add(
                "Seguridad",
                "Usuario",
                idUsuario=user_id,
                codigo=code,
                nombre=name,
                clave=clave,
                administrador=admin,
                estado=True,
            )
            for form_id, module in forms:
                if modules is None or module.upper() in modules:
                    self.add(
                        "Seguridad",
                        "PermisoFormulario",
                        idPermisoFormulario=permiso,
                        idUsuario=user_id,
                        idFormulario=form_id,
                        estado=True,
                    )
                    permiso += 1
            summary.append(
                (code, "administrador" if admin else ", ".join(sorted(modules or [])), name)
            )
        return summary


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------


def make_logo() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (600, 180), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 170, 170), fill=(20, 33, 61, 255))
    draw.ellipse((48, 48, 132, 132), fill=(255, 255, 255, 255))
    draw.ellipse((72, 72, 108, 108), fill=(232, 93, 4, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", 64)
        small = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = small = ImageFont.load_default()
    draw.text((195, 30), "RODAMUNDO", font=font, fill=(20, 33, 61, 255))
    draw.text((198, 112), "LLANTAS · RINES · SERVICIO", font=small, fill=(232, 93, 4, 255))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------


async def connect(database: str) -> asyncpg.Connection:
    return await asyncpg.connect(database=database)


def run_pg(pg_bin: Path, tool: str, *args: str) -> None:
    exe = pg_bin / (tool + (".exe" if os.name == "nt" else ""))
    result = subprocess.run(
        [str(exe), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise SystemExit(f"{tool} falló:\n{result.stderr[-3000:]}")


async def create_database(source: str, target: str, pg_bin: Path, replace: bool) -> None:
    admin = await connect("postgres")
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", target)
        if exists:
            if not replace:
                raise SystemExit(f"La base {target} ya existe. Use --replace para rehacerla.")
            await admin.execute(f'DROP DATABASE "{target}"')
        await admin.execute(f"CREATE DATABASE \"{target}\" ENCODING 'UTF8' TEMPLATE template0")
    finally:
        await admin.close()
    with tempfile.TemporaryDirectory() as tmp:
        schema = Path(tmp) / "schema.sql"
        run_pg(
            pg_bin,
            "pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "-d",
            source,
            "-f",
            str(schema),
        )
        run_pg(pg_bin, "psql", "-q", "-v", "ON_ERROR_STOP=1", "-d", target, "-f", str(schema))


async def copy_catalogs(source: str, target: str) -> None:
    src, dst = await connect(source), await connect(target)
    try:
        copied = {f"{s}.{t}" for s, t in COPIED_TABLES}
        for schema, table in COPIED_TABLES:
            columns = [
                r["column_name"]
                for r in await src.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = $1 AND table_name = $2 ORDER BY ordinal_position",
                    schema,
                    table,
                )
            ]
            # Llaves foráneas hacia tablas que no se copian: quedan en NULL.
            foreign = {
                r["c"]
                for r in await src.fetch(
                    """SELECT kcu.column_name c, ccu.table_schema || '.' || ccu.table_name r
                   FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu
                     ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                   JOIN information_schema.constraint_column_usage ccu
                     ON tc.constraint_name = ccu.constraint_name
                  WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = $1 AND tc.table_name = $2""",
                    schema,
                    table,
                )
                if r["r"] not in copied
            }
            # Los usuarios de la auditoría son de la base de origen: pasan al
            # administrador de la demo (idUsuario 1).
            audit = {c for c in columns if c.startswith("idUsuario")}
            select = ", ".join(
                "1" if c in audit else "NULL" if c in foreign else f'"{c}"' for c in columns
            )
            records = await src.fetch(f'SELECT {select} FROM "{schema}"."{table}"')
            await dst.copy_records_to_table(
                table, schema_name=schema, columns=columns, records=[tuple(r) for r in records]
            )
    finally:
        await src.close()
        await dst.close()


INSERT_ORDER = [
    ("Empresa", "Empresa"),
    ("Empresa", "CentroCosto"),
    ("Inventario", "Almacen"),
    ("SEO", "Modulo"),
    ("General", "Documento"),
    ("Inventario", "Grupo"),
    ("Inventario", "Producto"),
    ("Tercero", "Tercero"),
    ("Seguridad", "Usuario"),
    ("Seguridad", "PermisoFormulario"),
    ("CuentaCobrar", "Factura"),
    ("CuentaCobrar", "DetalleFactura"),
    ("CuentaPagar", "FacturaCompra"),
    ("CuentaPagar", "DetalleFacturaCompra"),
    ("Cartera", "FacturaTercero"),
    ("Inventario", "SaldoInventario"),
]


def coerce(value: Any, data_type: str) -> Any:
    """Ajusta el valor al tipo real de la columna: asyncpg no convierte solo."""
    if value is None:
        return None
    if data_type == "boolean":
        return bool(value)
    if data_type == "date" and isinstance(value, datetime):
        return value.date()
    if data_type.startswith("timestamp") and type(value) is date:
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if data_type == "timestamp without time zone" and isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if data_type in ("integer", "bigint", "smallint") and not isinstance(value, bool):
        return int(value)
    if data_type in ("numeric", "money"):
        return Decimal(value)
    if data_type in ("double precision", "real"):
        return float(value)
    if data_type in ("character", "character varying", "text") and not isinstance(value, str):
        return str(value)
    return value


async def load(target: str, demo: Demo) -> None:
    conn = await connect(target)
    try:
        async with conn.transaction():
            for schema, table in INSERT_ORDER:
                rows = demo.rows.get((schema, table), [])
                if not rows:
                    continue
                columns = list(dict.fromkeys(c for r in rows for c in r))
                types = {
                    r["column_name"]: r["data_type"]
                    for r in await conn.fetch(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = $1 AND table_name = $2",
                        schema,
                        table,
                    )
                }
                # El ERP pone 0 por defecto en algunas llaves foráneas, y en una base
                # nueva ese id no existe. Las que no se llenan quedan en NULL.
                loose = [
                    r["column_name"]
                    for r in await conn.fetch(
                        """SELECT DISTINCT kcu.column_name
                       FROM information_schema.table_constraints tc
                       JOIN information_schema.key_column_usage kcu
                         ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                       JOIN information_schema.columns col
                         ON col.table_schema = kcu.table_schema
                        AND col.table_name = kcu.table_name
                        AND col.column_name = kcu.column_name
                      WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_schema = $1 AND tc.table_name = $2
                        AND col.column_default IS NOT NULL AND col.is_nullable = 'YES'""",
                        schema,
                        table,
                    )
                ]
                columns += [c for c in loose if c not in columns]
                unknown = [c for c in columns if c not in types]
                if unknown:
                    raise SystemExit(f"{schema}.{table} no tiene las columnas {unknown}")
                try:
                    await conn.copy_records_to_table(
                        table,
                        schema_name=schema,
                        columns=columns,
                        records=[tuple(coerce(r.get(c), types[c]) for c in columns) for r in rows],
                    )
                except (asyncpg.PostgresError, TypeError, ValueError) as exc:
                    raise SystemExit(f"No se pudo cargar {schema}.{table}: {exc}") from exc
            # Las secuencias siguen desde el último id cargado.
            sequences = await conn.fetch(
                """SELECT n.nspname s, c.relname t, a.attname col,
                          pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname),
                                                 a.attname) seq
                   FROM pg_attribute a
                   JOIN pg_class c ON c.oid = a.attrelid AND c.relkind = 'r'
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE a.attnum > 0 AND NOT a.attisdropped
                    AND n.nspname NOT IN ('pg_catalog', 'information_schema')"""
            )
            for row in sequences:
                if row["seq"]:
                    table_ref = f'"{row["s"]}"."{row["t"]}"'
                    await conn.execute(
                        f"""SELECT setval('{row["seq"]}',
                               COALESCE((SELECT MAX("{row["col"]}") FROM {table_ref}), 0) + 1,
                               false)"""
                    )
    finally:
        await conn.close()


async def municipios(source: str) -> dict[str, int]:
    conn = await connect(source)
    try:
        # El código del municipio viene sin el del departamento: '001' es la
        # capital de cualquiera. La llave completa es departamento + municipio.
        return {
            r["dane"]: r["idMunicipio"]
            for r in await conn.fetch(
                'SELECT m."idMunicipio", TRIM(d."codigoDane") || TRIM(m."codigoDane") AS dane '
                'FROM "General"."Municipio" m '
                'JOIN "General"."Departamento" d USING ("idDepartamento")'
            )
        }
    finally:
        await conn.close()


async def forms(target: str) -> list[tuple[int, str]]:
    conn = await connect(target)
    try:
        return [
            (r["idFormulario"], r["modulo"])
            for r in await conn.fetch(
                'SELECT "idFormulario", modulo FROM "Seguridad"."Formulario" WHERE estado'
            )
        ]
    finally:
        await conn.close()


async def summary(target: str) -> None:
    conn = await connect(target)
    try:
        for label, sql in [
            ("Productos", 'SELECT count(*) FROM "Inventario"."Producto"'),
            ("Terceros", 'SELECT count(*) FROM "Tercero"."Tercero"'),
            ("Facturas de venta", 'SELECT count(*) FROM "CuentaCobrar"."Factura"'),
            ("Facturas de compra", 'SELECT count(*) FROM "CuentaPagar"."FacturaCompra"'),
            ("Saldos de inventario", 'SELECT count(*) FROM "Inventario"."SaldoInventario"'),
            (
                "Cartera con saldo",
                'SELECT count(*) FROM "Cartera"."FacturaTercero" WHERE "valorSaldo" > 0',
            ),
            (
                "Ventas totales",
                "SELECT to_char(sum(total), 'FM999G999G999G999') "
                'FROM "CuentaCobrar"."Factura" WHERE NOT anulada',
            ),
        ]:
            print(f"  {label}: {await conn.fetchval(sql)}")
    finally:
        await conn.close()


async def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", required=True, help="base del ERP de donde sale la estructura")
    parser.add_argument("--target", default="savi_demo_erp", help="base nueva (debe decir 'demo')")
    parser.add_argument("--pg-bin", type=Path, required=True, help="carpeta de pg_dump y psql")
    parser.add_argument("--replace", action="store_true", help="borra la base destino si existe")
    parser.add_argument("--dump", type=Path, help="además, deja un volcado restaurable aquí")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    if not _SAFE_TARGET.match(args.target):
        raise SystemExit("El nombre de la base destino debe contener 'demo' (minúsculas).")
    if args.target == args.source:
        raise SystemExit("La base destino no puede ser la de origen.")

    print(f"1/5 Estructura de {args.source} en {args.target}")
    await create_database(args.source, args.target, args.pg_bin, args.replace)
    print("2/5 Catálogos públicos y del ERP")
    await copy_catalogs(args.source, args.target)
    print("3/5 Datos inventados")
    demo = Demo(await municipios(args.target))
    demo.company(make_logo())
    demo.thirds_all()
    demo.catalog()
    demo.movements()
    users = demo.users(await forms(args.target))
    print("4/5 Carga")
    await load(args.target, demo)
    await summary(args.target)
    if args.dump:
        print(f"5/5 Volcado en {args.dump}")
        run_pg(
            args.pg_bin,
            "pg_dump",
            "--no-owner",
            "--no-privileges",
            "-Fc",
            "-d",
            args.target,
            "-f",
            str(args.dump),
        )
    else:
        print("5/5 Sin volcado (use --dump)")
    print(f"\nUsuarios de la demo (clave {DEMO_PASSWORD}):")
    for code, access, name in users:
        print(f"  {code:<10} {name:<22} {access}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
