from datetime import timedelta

from app.modules.cloud_link.domain.entities import EPOCH, Cursor, StreamWatermark

# Relectura por ciclo (S3): un writer puede confirmar un mensaje con
# `created_at` anterior a la marca ya avanzada.
REREAD_WINDOW = timedelta(minutes=15)


def start_cursor(watermark: StreamWatermark | None, window: timedelta = REREAD_WINDOW) -> Cursor:
    """Desde dónde lee un ciclo.

    Con la marca inicial (sin ninguna fila vista, `id` vacío) no se relee: una
    vinculación "solo desde hoy" no debe enviar lo anterior al vínculo.
    """
    if watermark is None:
        return Cursor(EPOCH, "")
    if not watermark.id:
        return Cursor(watermark.at, "")
    return Cursor(watermark.at - window, "")
