"""Errores tipados del módulo free_query.

El mensaje de cada uno es el texto que verá el LLM como `tool_result.isError`.
Está pensado para ser **accionable**: que el modelo pueda corregir el SQL
en el siguiente turno sin caer en bucles.
"""
from __future__ import annotations

from enum import StrEnum


class RejectionReason(StrEnum):
    """Resultado de la auditoría — codificado para queries analíticas."""

    OK = "ok"
    REJECTED_AST = "rechazado_ast"
    REJECTED_EXPLAIN = "rechazado_explain"
    RATE_LIMITED = "rate_limited"
    DB_ERROR = "db_error"


class FreeQueryError(Exception):
    """Base de errores del módulo. Contiene el motivo para auditoría."""

    reason: RejectionReason = RejectionReason.DB_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AstValidationError(FreeQueryError):
    """El SQL no pasó las reglas estructurales (sqlglot)."""

    reason = RejectionReason.REJECTED_AST


class ExplainGateError(FreeQueryError):
    """El plan estima demasiadas filas — la consulta es muy amplia."""

    reason = RejectionReason.REJECTED_EXPLAIN


class DatabaseExecutionError(FreeQueryError):
    """Postgres devolvió un error al ejecutar la query."""

    reason = RejectionReason.DB_ERROR
