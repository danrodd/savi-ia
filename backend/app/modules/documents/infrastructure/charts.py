"""Gráfico de barras para los documentos, dibujado con Pillow.

Una imagen PNG que sirve igual para el PDF y para el Word. Los valores salen
del conjunto de resultados (de la base), nunca del texto del modelo.
"""

from __future__ import annotations

import io
from typing import Any

MAX_BARS = 15
_WIDTH = 1400
_ROW = 46
_TOP = 90
_LABEL_WIDTH = 520
_BRAND = (185, 28, 28)
_INK = (29, 26, 25)
_MUTED = (110, 102, 98)
_GRID = (228, 223, 220)


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


def bar_chart_png(title: str, items: list[tuple[str, float]]) -> bytes:
    """Barras horizontales de los `MAX_BARS` valores mayores, de mayor a menor."""
    from PIL import Image, ImageDraw

    top = sorted(items, key=lambda item: item[1], reverse=True)[:MAX_BARS]
    height = _TOP + _ROW * max(len(top), 1) + 40
    image = Image.new("RGB", (_WIDTH, height), "white")
    draw = ImageDraw.Draw(image)
    title_font, label_font = _font(34), _font(24)
    draw.text((30, 24), _fit(draw, title, title_font, _WIDTH - 60), fill=_INK, font=title_font)
    peak = max((value for _, value in top), default=0) or 1
    bar_area = _WIDTH - _LABEL_WIDTH - 200
    for index, (label, value) in enumerate(top):
        y = _TOP + index * _ROW
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
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
