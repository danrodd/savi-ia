"""Presentación de la empresa para los documentos: nombre y logo del ERP.

El ERP ya guarda los dos en `Empresa.Empresa` (`razonSocial` y `logo`), así que
no hace falta que el administrador los vuelva a cargar en SAVI.

El logo es un binario que viene de la base: antes de meterlo en un PDF o un
Word se decodifica con Pillow, se achica y se vuelve a codificar como PNG. Un
archivo dañado o que no es una imagen se descarta, y el documento sale sin logo.
"""

from __future__ import annotations

import io
import logging
from uuid import UUID

from sqlalchemy import text

from app.modules.documents.domain.document import Branding
from app.modules.erp_databases.infrastructure import get_erp_engine_for

log = logging.getLogger(__name__)

_SQL = (
    'SELECT NULLIF(TRIM("razonSocial"), \'\') AS name, "logo" FROM "Empresa"."Empresa" '
    'ORDER BY "idEmpresa" LIMIT 1'
)
# Logos de más de esto no se procesan: es más que cualquier logo razonable.
MAX_LOGO_BYTES = 8 * 1024 * 1024
LOGO_MAX_SIDE = 400
# Protección contra imágenes "bomba" (pocos bytes, millones de píxeles).
_MAX_PIXELS = 40_000_000


def normalize_logo(raw: bytes | None) -> bytes | None:
    """PNG de hasta `LOGO_MAX_SIDE` píxeles de lado, o `None` si no es una imagen válida."""
    if not raw or len(raw) > MAX_LOGO_BYTES:
        return None
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = _MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            converted = image.convert("RGBA")
            converted.thumbnail((LOGO_MAX_SIDE, LOGO_MAX_SIDE))
            out = io.BytesIO()
            converted.save(out, format="PNG")
            return out.getvalue()
    except Exception:  # noqa: BLE001 — cualquier cosa rara: sin logo
        log.warning("company_logo_unreadable")
        return None


async def read_branding(erp_database_id: UUID | None) -> Branding:
    try:
        engine = await get_erp_engine_for(erp_database_id)
        async with engine.connect() as conn:
            row = (await conn.execute(text(_SQL))).mappings().first()
    except Exception:  # noqa: BLE001 — sin presentación, el documento sale igual
        log.warning("company_branding_unavailable", exc_info=True)
        return Branding()
    if row is None:
        return Branding()
    logo = row["logo"]
    return Branding(
        name=str(row["name"]) if row["name"] else None,
        logo_png=normalize_logo(bytes(logo) if logo is not None else None),
    )
