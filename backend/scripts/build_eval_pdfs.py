# ruff: noqa: E501 — el texto de los documentos se conserva con sus líneas originales.
"""Genera los PDF sintéticos del set de evaluación de documentos de la empresa.

Uso (reproducible, sin dependencias nuevas):

    uv run python -m scripts.build_eval_pdfs

Escribe PDF 1.4 a mano: una fuente Helvetica con `WinAnsiEncoding` (tildes y
eñes), varias líneas por página y un encabezado repetido en todas las páginas
para ejercitar la eliminación de encabezados del extractor.

Los documentos son de una empresa FICTICIA. No contienen datos de clientes.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

OUT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "company_knowledge"
    / "eval"
    / "documents"
)
HEADER = "DROGUERÍA ANDINA S.A.S. · Documento controlado"
WRAP = 88

DOCUMENTS: dict[str, list[str]] = {
    "reglamento-trabajo.pdf": [
        """REGLAMENTO INTERNO DE TRABAJO — CAPÍTULO III: JORNADA Y ASISTENCIA

Artículo 18. Horario. La jornada ordinaria en las sedes es de lunes a sábado en dos turnos:
el turno de la mañana de 6:00 a. m. a 2:00 p. m. y el turno de la tarde de 2:00 p. m. a 10:00 p. m.
El personal administrativo trabaja de lunes a viernes de 8:00 a. m. a 5:30 p. m. con una hora de almuerzo.

Artículo 19. Registro de asistencia. Todo empleado registra su entrada y su salida en el lector
biométrico de la sede. Olvidar el registro se reporta al jefe inmediato el mismo día.

Artículo 20. Llegadas tarde. Se considera llegada tarde el ingreso con más de 10 minutos de retraso.
Tres llegadas tarde en un mismo mes dan lugar a un llamado de atención escrito (memorando).
La reincidencia en el mes siguiente se trata como falta disciplinaria.""",
        """CAPÍTULO IV: VACACIONES Y PERMISOS

Artículo 24. Vacaciones. Cada empleado tiene derecho a 15 días hábiles de vacaciones remuneradas
por cada año de servicio. La solicitud se radica en el portal de Gestión Humana con un mínimo de
30 días de anticipación y la aprueba el jefe inmediato. No se pueden acumular más de dos períodos.

Artículo 25. Permisos. Los permisos para citas médicas se conceden con la presentación del
soporte de la cita. Los permisos personales de hasta medio día los autoriza el jefe inmediato;
los de un día completo o más, Gestión Humana.

Artículo 26. Licencia por calamidad doméstica. Se conceden hasta 3 días hábiles remunerados
por calamidad doméstica debidamente comprobada.""",
        """CAPÍTULO V: PRESENTACIÓN PERSONAL Y HORAS EXTRA

Artículo 30. Uniforme. El personal de sede usa la bata blanca institucional con el carné visible
durante todo el turno. El calzado es cerrado y antideslizante. No se permite el uso de joyas
colgantes en el área de dispensación.

Artículo 31. Horas extra. Las horas extra solo se pagan si fueron autorizadas por escrito por el
director de la sede ANTES de trabajarlas. El máximo es de 12 horas extra por semana.
Las horas extra no autorizadas no se reconocen en la nómina.""",
        """CAPÍTULO VI: CANALES DE COMUNICACIÓN

Artículo 35. Quejas y sugerencias. Los empleados pueden presentar quejas o sugerencias por el buzón
físico de cada sede o por el correo gestionhumana@drogueriaandina.example. Las quejas de acoso laboral
se presentan ante el Comité de Convivencia Laboral, que responde en un máximo de 10 días hábiles.

Artículo 36. Comunicaciones oficiales. Las circulares y los cambios de este reglamento se publican en la
cartelera de cada sede y en el portal de Gestión Humana.""",
    ],
    "procedimiento-inventario.pdf": [
        """PROCEDIMIENTO DE CONTROL DE INVENTARIO — PR-INV-03

1. Objetivo. Mantener existencias exactas, evitar pérdidas por vencimiento y garantizar la
conservación de los medicamentos que requieren cadena de frío.

2. Conteo cíclico. Cada sede cuenta mensualmente las referencias de mayor rotación y cada
trimestre el inventario completo. El conteo se hace fuera del horario de atención y con dos
personas: una cuenta y la otra registra.

3. Diferencias. Si la diferencia entre el conteo físico y el sistema supera el 2% del valor de
la referencia, se hace un segundo conteo. Si la diferencia persiste, se reporta a la
Coordinación de Operaciones antes de ajustar el inventario.""",
        """4. Productos próximos a vencer. Los productos se retiran de la exhibición 90 días antes de su
fecha de vencimiento y se ubican en la zona de devoluciones a proveedor. Los que el proveedor no
recibe se destruyen con acta firmada por el director de la sede y el químico farmacéutico.

5. Cadena de frío. Las neveras de medicamentos deben mantenerse entre 2 °C y 8 °C. La temperatura
se registra cada 4 horas en el formato FO-INV-07. Si la temperatura sale del rango por más de
30 minutos, los productos se ponen en cuarentena y se consulta a Calidad antes de venderlos.""",
        """6. Recepción de mercancía. Al recibir un pedido se verifica la cantidad, el número de lote, la
fecha de vencimiento y la integridad del empaque contra la factura del proveedor. No se reciben
productos con menos de 12 meses de vida útil sin autorización de Compras.

7. Responsables. El director de la sede responde por la exactitud del inventario; el químico
farmacéutico, por la cadena de frío y la destrucción de productos vencidos.""",
    ],
    "protocolo-controlados.pdf": [
        """PROTOCOLO DE DISPENSACIÓN DE MEDICAMENTOS DE CONTROL ESPECIAL

1. Alcance. Aplica a los medicamentos de control especial definidos por el Fondo Nacional de
Estupefacientes (FNE) que maneja la droguería.

2. Fórmula médica. Solo se dispensan con la fórmula médica original, en el recetario oficial,
con nombre completo del paciente, documento de identidad, dosis y firma del médico. No se aceptan
fotocopias ni fórmulas enviadas por correo o mensajería.

3. Registro. Cada dispensación se anota el mismo día en el libro oficial de control, con el número
de la fórmula, el paciente, la cantidad entregada y el saldo resultante.""",
        """4. Almacenamiento. Los medicamentos de control especial se guardan en un armario metálico con
doble llave. Una llave la tiene el químico farmacéutico y la otra el director de la sede.

5. Reporte mensual. Dentro de los primeros 10 días de cada mes se envía al FNE el informe de
movimientos del mes anterior. El químico farmacéutico es responsable del envío.

6. Faltantes. Cualquier faltante en el armario de controlados se reporta el mismo día a la
Gerencia y a la autoridad sanitaria; nunca se ajusta el inventario sin esa denuncia.""",
    ],
}


def _encode(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return escaped.encode("cp1252")


def _page_stream(body: str) -> bytes:
    lines = [HEADER, ""]
    for paragraph in body.strip().split("\n\n"):
        lines.extend(textwrap.wrap(" ".join(paragraph.split()), WRAP))
        lines.append("")
    ops = [b"BT", b"/F1 10 Tf", b"14 TL", b"56 760 Td"]
    for line in lines:
        ops.append(b"(" + _encode(line) + b") Tj T*")
    ops.append(b"ET")
    return b"\n".join(ops)


def build_pdf(pages: list[str]) -> bytes:
    objects: list[bytes] = []
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for index, body in enumerate(pages):
        content_id = page_ids[index] + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        stream = _page_stream(body)
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, pages in DOCUMENTS.items():
        (OUT / name).write_bytes(build_pdf(pages))
        print(f"{name}: {len(pages)} páginas")


if __name__ == "__main__":
    main()
