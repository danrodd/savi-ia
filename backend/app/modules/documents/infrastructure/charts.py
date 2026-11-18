"""Gráficos para los documentos, dibujados con Pillow.

Una imagen PNG que sirve igual para el PDF y para el Word. Los valores salen
del conjunto de resultados (de la base), nunca del texto del modelo.

Tres formas:
- barras: los `MAX_BARS` valores mayores, de mayor a menor. Si hay más, el
  gráfico lo dice debajo del título en vez de cortarlos en silencio.
- torta: las `MAX_SLICES` porciones mayores y el resto sumado en "Otros", para
  que los porcentajes cuadren con el total.
- líneas: los puntos en el orden de la consulta (por ejemplo, por mes).
"""

from __future__ import annotations

import io
import math
from typing import Any

from app.modules.documents.domain.document import MAX_LINE_POINTS, ChartShape

MAX_BARS = 15
MAX_SLICES = 7

_WIDTH = 1400
_ROW = 46
_TOP = 90
_LABEL_WIDTH = 520
_BRAND = (185, 28, 28)
_INK = (29, 26, 25)
_MUTED = (110, 102, 98)
_GRID = (228, 223, 220)
_WHITE = (255, 255, 255)
# Paleta categórica en orden fijo, validada para daltonismo sobre fondo claro.
# "Otros" va siempre en gris: es el resto, no una categoría más.
_SERIES = (
    (42, 120, 214),
    (235, 104, 52),
    (27, 175, 122),
    (237, 161, 0),
    (232, 123, 164),
    (0, 131, 0),
    (98, 80, 214),
)
_OTHERS = (181, 179, 173)


def _font(size: int) -> Any:
    from PIL import ImageFont

    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _amount(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fit(draw: Any, text: str, font: Any, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _png(image: Any) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def chart_png(shape: ChartShape, title: str, items: list[tuple[str, float]]) -> bytes:
    """El gráfico de la forma pedida, con `items` como (etiqueta, valor)."""
    if shape == "pie":
        return pie_chart_png(title, items)
    if shape == "line":
        return line_chart_png(title, items)
    return bar_chart_png(title, items)


def bar_chart_png(title: str, items: list[tuple[str, float]]) -> bytes:
    """Barras horizontales de los `MAX_BARS` valores mayores, de mayor a menor."""
    from PIL import Image, ImageDraw

    top = sorted(items, key=lambda item: item[1], reverse=True)[:MAX_BARS]
    hidden = len(items) - len(top)
    top_offset = _TOP + (34 if hidden else 0)
    height = top_offset + _ROW * max(len(top), 1) + 40
    image = Image.new("RGB", (_WIDTH, height), "white")
    draw = ImageDraw.Draw(image)
    title_font, label_font = _font(34), _font(24)
    draw.text((30, 24), _fit(draw, title, title_font, _WIDTH - 60), fill=_INK, font=title_font)
    if hidden:
        draw.text(
            (30, 72),
            f"Se muestran los {len(top)} mayores de {len(items)}.",
            fill=_MUTED,
            font=label_font,
        )
    peak = max((value for _, value in top), default=0) or 1
    bar_area = _WIDTH - _LABEL_WIDTH - 200
    for index, (label, value) in enumerate(top):
        y = top_offset + index * _ROW
        draw.text(
            (30, y + 8),
            _fit(draw, label, label_font, _LABEL_WIDTH - 50),
            fill=_INK,
            font=label_font,
        )
        draw.line((_LABEL_WIDTH, y + _ROW - 2, _WIDTH - 30, y + _ROW - 2), fill=_GRID)
        length = max(int(bar_area * max(value, 0) / peak), 2)
        draw.rectangle((_LABEL_WIDTH, y + 8, _LABEL_WIDTH + length, y + _ROW - 10), fill=_BRAND)
        draw.text((_LABEL_WIDTH + length + 12, y + 8), _amount(value), fill=_MUTED, font=label_font)
    return _png(image)


def pie_slices(items: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Las porciones mayores y el resto sumado en "Otros"; sin valores en cero."""
    positive = sorted(
        ((label, value) for label, value in items if value > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    if len(positive) <= MAX_SLICES + 1:
        return positive
    top = positive[:MAX_SLICES]
    rest = positive[MAX_SLICES:]
    return [*top, (f"Otros ({len(rest)})", sum(value for _, value in rest))]


def pie_chart_png(title: str, items: list[tuple[str, float]]) -> bytes:
    """Torta con leyenda: etiqueta, valor y porcentaje de cada porción."""
    from PIL import Image, ImageDraw

    slices = pie_slices(items)
    total = sum(value for _, value in slices)
    # Se dibuja al doble y se reduce: Pillow no suaviza los bordes de la torta.
    scale = 2
    diameter = 520
    legend_rows = max(len(slices), 1)
    height = max(_TOP + diameter + 60, _TOP + 30 + legend_rows * 54 + 40)
    image = Image.new("RGB", (_WIDTH * scale, height * scale), "white")
    draw = ImageDraw.Draw(image)
    title_font, label_font = _font(34 * scale), _font(24 * scale)
    draw.text(
        (30 * scale, 24 * scale),
        _fit(draw, title, title_font, (_WIDTH - 60) * scale),
        fill=_INK,
        font=title_font,
    )
    box = (60 * scale, (_TOP + 20) * scale, (60 + diameter) * scale, (_TOP + 20 + diameter) * scale)
    if total <= 0:
        draw.text(
            (60 * scale, (_TOP + 40) * scale),
            "No hay valores mayores que cero para graficar.",
            fill=_MUTED,
            font=label_font,
        )
    else:
        start = -90.0
        for index, (label, value) in enumerate(slices):
            sweep = 360.0 * value / total
            color = _OTHERS if label.startswith("Otros (") else _SERIES[index % len(_SERIES)]
            draw.pieslice(box, start, start + sweep, fill=color, outline=_WHITE, width=3 * scale)
            start += sweep
        legend_x = (60 + diameter + 80) * scale
        for index, (label, value) in enumerate(slices):
            y = (_TOP + 30 + index * 54) * scale
            color = _OTHERS if label.startswith("Otros (") else _SERIES[index % len(_SERIES)]
            draw.rounded_rectangle(
                (legend_x, y + 4 * scale, legend_x + 26 * scale, y + 30 * scale),
                radius=4 * scale,
                fill=color,
            )
            percent = f"{value / total * 100:.1f}".replace(".", ",")
            share = f"{_amount(value)}  ·  {percent} %"
            text_x = legend_x + 42 * scale
            share_width = int(draw.textlength(share, font=label_font))
            label_width = (_WIDTH - 40) * scale - text_x - share_width - 24 * scale
            draw.text(
                (text_x, y), _fit(draw, label, label_font, label_width), fill=_INK, font=label_font
            )
            draw.text(((_WIDTH - 40) * scale - share_width, y), share, fill=_MUTED, font=label_font)
    return _png(image.resize((_WIDTH, height), Image.Resampling.LANCZOS))


def nice_ticks(low: float, high: float, target: int = 4) -> list[float]:
    """Marcas redondas (1, 2, 2,5 o 5 por potencia de diez) que cubren el rango."""
    if high <= low:
        high = low + 1
    rough = (high - low) / target
    magnitude = 10 ** math.floor(math.log10(rough))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= rough)
    start = math.floor(low / step) * step
    end = math.ceil(high / step) * step
    count = round((end - start) / step)
    return [start + i * step for i in range(count + 1)]


def line_chart_png(title: str, items: list[tuple[str, float]]) -> bytes:
    """Línea con los puntos en el orden recibido; eje vertical desde cero."""
    from PIL import Image, ImageDraw

    points = items[:MAX_LINE_POINTS]
    scale = 2
    height = 640
    left, right, top, bottom = 170, _WIDTH - 50, _TOP + 20, height - 90
    image = Image.new("RGB", (_WIDTH * scale, height * scale), "white")
    draw = ImageDraw.Draw(image)
    title_font, label_font = _font(34 * scale), _font(22 * scale)
    draw.text(
        (30 * scale, 24 * scale),
        _fit(draw, title, title_font, (_WIDTH - 60) * scale),
        fill=_INK,
        font=title_font,
    )
    if not points:
        draw.text(
            (30 * scale, (_TOP + 20) * scale),
            "No hay valores para graficar.",
            fill=_MUTED,
            font=label_font,
        )
        return _png(image.resize((_WIDTH, height), Image.Resampling.LANCZOS))

    values = [value for _, value in points]
    ticks = nice_ticks(min(0.0, min(values)), max(0.0, max(values)))
    low, high = ticks[0], ticks[-1]

    def y_of(value: float) -> float:
        return bottom - (value - low) / (high - low) * (bottom - top)

    def x_of(index: int) -> float:
        if len(points) == 1:
            return (left + right) / 2
        return left + index * (right - left) / (len(points) - 1)

    # Cuadrícula tenue con marcas redondas y su valor a la izquierda.
    for value in ticks:
        y = y_of(value) * scale
        draw.line((left * scale, y, right * scale, y), fill=_GRID, width=scale)
        text = _amount(value)
        width = draw.textlength(text, font=label_font)
        draw.text(
            (left * scale - width - 14 * scale, y - 13 * scale), text, fill=_MUTED, font=label_font
        )

    # Etiquetas del eje horizontal: como mucho ocho, a intervalos iguales contados
    # desde el último punto (el más reciente siempre lleva etiqueta y no se pisan).
    every = max(1, -(-len(points) // 8))
    for index in range(len(points) - 1, -1, -every):
        label = points[index][0]
        text = _fit(draw, label, label_font, 150 * scale)
        width = draw.textlength(text, font=label_font)
        x = x_of(index) * scale - width / 2
        x = min(max(x, 10 * scale), (_WIDTH - 10) * scale - width)
        draw.text((x, (bottom + 18) * scale), text, fill=_MUTED, font=label_font)

    coords = [(x_of(i) * scale, y_of(v) * scale) for i, v in enumerate(values)]
    if len(coords) > 1:
        draw.line(coords, fill=_BRAND, width=4 * scale, joint="curve")
    if len(coords) <= 24:
        radius = 6 * scale
        for x, y in coords:
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=_BRAND,
                outline=_WHITE,
                width=2 * scale,
            )
    # Solo el último valor lleva etiqueta: un número en cada punto satura.
    last_x, last_y = coords[-1]
    last = _amount(values[-1])
    width = draw.textlength(last, font=label_font)
    draw.text(
        (min(last_x - width / 2, (_WIDTH - 10) * scale - width), last_y - 44 * scale),
        last,
        fill=_INK,
        font=label_font,
    )
    return _png(image.resize((_WIDTH, height), Image.Resampling.LANCZOS))
