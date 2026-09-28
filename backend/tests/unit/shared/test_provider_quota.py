"""Qué significa un 429 del proveedor: esperar, cambiar de modelo o cargar saldo."""

from __future__ import annotations

import pytest

from app.shared.provider_quota import QuotaFailure, classify_quota_error

# Mensaje real del límite por minuto de Gemini (2026-09-28): dice "billing"
# aunque no sea un problema de saldo.
_GEMINI_MESSAGE = (
    "You exceeded your current quota, please check your plan and billing details. "
    "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_requests_per_model"
)


class _OpenAIError(Exception):
    def __init__(self, status_code: int, body: object = None) -> None:
        super().__init__("error")
        self.status_code = status_code
        self.body = body


class _GeminiError(Exception):
    def __init__(self, code: int, message: str, quota_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = (
            {
                "error": {
                    "details": [
                        {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": quota_id}],
                        },
                        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "49s"},
                    ]
                }
            }
            if quota_id
            else None
        )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_OpenAIError(429), QuotaFailure.RATE_LIMIT),
        (_OpenAIError(429, {"code": "insufficient_quota"}), QuotaFailure.NO_CREDITS),
        (
            _OpenAIError(429, {"error": {"type": "insufficient_quota", "code": None}}),
            QuotaFailure.NO_CREDITS,
        ),
        (
            _OpenAIError(429, {"error": {"code": "credit_balance_exhausted"}}),
            QuotaFailure.NO_CREDITS,
        ),
        (
            _GeminiError(429, _GEMINI_MESSAGE, "GenerateRequestsPerMinutePerProjectPerModel"),
            QuotaFailure.RATE_LIMIT,
        ),
        (
            _GeminiError(429, _GEMINI_MESSAGE, "GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
            QuotaFailure.DAILY_QUOTA,
        ),
        (_GeminiError(429, "Your prepayment credits are depleted."), QuotaFailure.NO_CREDITS),
        # Sin detalle, un 429 se trata como pasajero: reintentar no rompe nada.
        (_GeminiError(429, _GEMINI_MESSAGE), QuotaFailure.RATE_LIMIT),
    ],
)
def test_a_429_is_classified_by_what_it_asks_for(error: Exception, expected: QuotaFailure) -> None:
    assert classify_quota_error(error) == expected


@pytest.mark.parametrize(
    "error",
    [_OpenAIError(401), _OpenAIError(503), _GeminiError(400, "prepayment credits"), ValueError()],
)
def test_anything_that_is_not_a_429_is_not_a_quota_problem(error: Exception) -> None:
    assert classify_quota_error(error) is None
