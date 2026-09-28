"""Traduce los errores de los SDK de proveedores a `AiReadingError`.

Solo mira el código HTTP y el tipo de excepción: nunca copia el mensaje del
proveedor, que puede traer fragmentos del pedido.
"""

import asyncio

from app.modules.company_knowledge.domain.exceptions import AiReadingError
from app.modules.company_knowledge.domain.value_objects import AiReadErrorCode
from app.shared.provider_quota import QuotaFailure, classify_quota_error

_AUTH_STATUS = (401, 403)
_TOO_LARGE_STATUS = (413,)


def status_of(error: BaseException) -> int | None:
    """OpenAI expone `status_code`; Gemini, `code`."""
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


def to_reading_error(error: BaseException) -> AiReadingError:
    if isinstance(error, AiReadingError):
        return error
    if isinstance(error, TimeoutError | asyncio.TimeoutError) or "Timeout" in type(error).__name__:
        return AiReadingError(AiReadErrorCode.TIMEOUT, retryable=True)
    status = status_of(error)
    quota = classify_quota_error(error)
    if quota == QuotaFailure.NO_CREDITS:
        # Saldo agotado: reintentar no lo arregla.
        return AiReadingError(AiReadErrorCode.NO_CREDITS, retryable=False)
    if quota == QuotaFailure.DAILY_QUOTA:
        return AiReadingError(AiReadErrorCode.DAILY_QUOTA, retryable=False)
    if quota == QuotaFailure.RATE_LIMIT:
        return AiReadingError(AiReadErrorCode.RATE_LIMITED, retryable=True)
    if status in _AUTH_STATUS:
        return AiReadingError(AiReadErrorCode.UNAVAILABLE, retryable=False)
    if status in _TOO_LARGE_STATUS:
        return AiReadingError(AiReadErrorCode.PAGE_TOO_LARGE, retryable=False)
    if status is not None and status >= 500:
        return AiReadingError(AiReadErrorCode.PROVIDER_ERROR, retryable=True)
    if status is not None:
        # 400 y afines: el pedido no va a mejorar repitiéndolo.
        return AiReadingError(AiReadErrorCode.PROVIDER_ERROR, retryable=False)
    # Sin código: caída de conexión o del proceso del CLI. Vale reintentar.
    return AiReadingError(AiReadErrorCode.PROVIDER_ERROR, retryable=True)
