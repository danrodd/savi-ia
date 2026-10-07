"""Procesamiento de imágenes adjuntas con Pillow.

El formato se decide por el CONTENIDO (Pillow lee la cabecera del archivo):
ni el nombre ni el `Content-Type` que declara el cliente se toman en cuenta.

Decisiones:
- Se corrige la orientación EXIF y se re-codifica, lo que además descarta
  los metadatos (ubicación GPS, modelo de cámara) antes de guardar.
- El lado mayor se reduce a `max_side_px`; nunca se agranda.
- GIF: se conserva solo el primer cuadro y se guarda como PNG. Ningún
  proveedor de IA interpreta la animación, y así se evita almacenar y
  enviar cuadros que no se usan.
"""

from __future__ import annotations

import io
import warnings

from PIL import Image, ImageOps

from app.modules.conversations.domain.exceptions import InvalidChatAttachmentError
from app.modules.conversations.domain.interfaces import ImageProcessor, ProcessedImage

_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
_MIME_BY_FORMAT = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
# Tope de píxeles declarados en la cabecera, chequeado ANTES de decodificar:
# una imagen pequeña en bytes puede expandirse a gigabytes de memoria.
_MAX_PIXELS = 50_000_000
_JPEG_QUALITY = 90
_WEBP_QUALITY = 90

_NOT_AN_IMAGE = "El archivo no es una imagen válida. Se aceptan PNG, JPEG, WEBP y GIF."


class PillowImageProcessor(ImageProcessor):
    def process(self, raw: bytes, *, max_side_px: int) -> ProcessedImage:
        try:
            # Pillow avisa (warning) antes de lanzar `DecompressionBombError`;
            # acá ya hay un tope propio, así que no se deja ensuciar el log.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                return self._process(raw, max_side_px)
        except InvalidChatAttachmentError:
            raise
        except Exception as exc:  # noqa: BLE001 — Pillow lanza de todo con basura
            raise InvalidChatAttachmentError(_NOT_AN_IMAGE) from exc

    @staticmethod
    def _process(raw: bytes, max_side_px: int) -> ProcessedImage:
        with Image.open(io.BytesIO(raw)) as opened:
            source_format = opened.format
            if source_format not in _ALLOWED_FORMATS:
                raise InvalidChatAttachmentError(_NOT_AN_IMAGE)
            if opened.width * opened.height > _MAX_PIXELS:
                raise InvalidChatAttachmentError("La imagen tiene dimensiones demasiado grandes.")
            opened.seek(0)  # GIF/WEBP animados: primer cuadro
            image: Image.Image = ImageOps.exif_transpose(opened)
            image.load()

        target_format = "PNG" if source_format == "GIF" else source_format
        assert target_format is not None  # noqa: S101 — filtrado arriba
        # Primero el modo: reducir una imagen con paleta (P) degrada a vecino
        # más cercano, y con LANCZOS hace falta RGB/RGBA.
        image = _normalize_mode(image, target_format)
        if max(image.size) > max_side_px:
            image.thumbnail((max_side_px, max_side_px), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if target_format == "JPEG":
            image.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        elif target_format == "WEBP":
            image.save(buffer, format="WEBP", quality=_WEBP_QUALITY)
        else:
            image.save(buffer, format="PNG", optimize=True)
        width, height = image.size
        return ProcessedImage(
            content=buffer.getvalue(),
            mime=_MIME_BY_FORMAT[target_format],
            width=width,
            height=height,
        )


def _normalize_mode(image: Image.Image, target_format: str) -> Image.Image:
    """Lleva la imagen a un modo que el formato destino pueda guardar."""
    if target_format == "JPEG":
        # JPEG no tiene transparencia: se aplana sobre blanco (convertir
        # directo dejaría el fondo transparente en negro).
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
            return flat
        return image if image.mode in ("RGB", "L") else image.convert("RGB")
    if image.mode in ("RGB", "RGBA", "L", "LA"):
        return image
    has_alpha = image.mode == "P" and "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")
