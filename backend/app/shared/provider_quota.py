"""Qué significa un 429 del proveedor de IA: esperar, cambiar de modelo o cargar saldo.

Los tres casos llegan con el mismo código HTTP y piden cosas distintas:

- **Límite pasajero** (pedidos por minuto): reintentar con espera lo resuelve.
- **Cuota diaria agotada** (Gemini): no vuelve hasta el día siguiente; otro
  modelo puede tener cuota propia.
- **Sin créditos**: nada se resuelve reintentando; un administrador tiene que
  cargar saldo.

Formas verificadas:

- OpenAI documenta `error.type = insufficient_quota` y el motivo en
  `error.code` (p. ej. `credit_balance_exhausted`).
- Gemini: el límite por minuto se capturó en vivo el 2026-09-28 (`quotaId`
  `GenerateRequestsPerMinutePerProjectPerModel` + `RetryInfo`). Ojo: su
  mensaje dice "check your plan and billing details" también en ese caso,
  así que "billing" NO sirve para detectar falta de saldo. Sin créditos
  prepagos el mensaje es "Your prepayment credits are depleted".
"""

from enum import StrEnum
from typing import Any, cast

_OPENAI_NO_CREDIT_CODES = ("credit_balance_exhausted", "insufficient_quota")
_GEMINI_NO_CREDIT_PHRASES = ("prepayment credits", "credits are depleted")


class QuotaFailure(StrEnum):
    RATE_LIMIT = "rate_limit"
    DAILY_QUOTA = "daily_quota"
    NO_CREDITS = "no_credits"


def _status(error: BaseException) -> int | None:
    # OpenAI expone `status_code`; Gemini, `code`.
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


def _as_dict(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _openai_no_credits(error: BaseException) -> bool:
    body = _as_dict(getattr(error, "body", None))
    # El SDK a veces entrega el objeto `error` y a veces el cuerpo completo.
    inner = _as_dict(body.get("error")) or body
    return (
        inner.get("code") in _OPENAI_NO_CREDIT_CODES
        or inner.get("type") == "insufficient_quota"
        or getattr(error, "code", None) in _OPENAI_NO_CREDIT_CODES
    )


def _gemini_quota_ids(error: BaseException) -> list[str]:
    details = _as_dict(getattr(error, "details", None))
    entries: list[Any] = _as_dict(details.get("error")).get("details") or []
    ids: list[str] = []
    for entry in entries:
        violations: list[Any] = _as_dict(entry).get("violations") or []
        for violation in violations:
            quota_id = _as_dict(violation).get("quotaId")
            if isinstance(quota_id, str):
                ids.append(quota_id)
    return ids


def classify_quota_error(error: BaseException) -> QuotaFailure | None:
    """`None` si no es un 429; si lo es, cuál de los tres casos."""
    if _status(error) != 429:
        return None
    if _openai_no_credits(error):
        return QuotaFailure.NO_CREDITS
    message = str(getattr(error, "message", None) or error).lower()
    if any(phrase in message for phrase in _GEMINI_NO_CREDIT_PHRASES):
        return QuotaFailure.NO_CREDITS
    if any("PerDay" in quota_id for quota_id in _gemini_quota_ids(error)):
        return QuotaFailure.DAILY_QUOTA
    return QuotaFailure.RATE_LIMIT
