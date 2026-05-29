"""Orquesta el ciclo de un SQL libre.

Pasos:
  1. validate_and_normalize → AST checks + LIMIT sanitizado.
  2. estimate_rows         → EXPLAIN gate (rechazo si > política).
  3. execute_select        → ejecuta y cap post-ejecución.
  4. auditor.record        → siempre, ok o rechazo.

Las excepciones tipadas (`AstValidationError`, `ExplainGateError`,
`DatabaseExecutionError`) cargan su propio `RejectionReason`, así que
el caller solo decide entre dos caminos: éxito o mensaje accionable
con `isError=True`.
"""
from __future__ import annotations

import logging
import re
import time
from uuid import UUID

from app.modules.free_query.application.sql_validator import validate_and_normalize
from app.modules.free_query.domain.errors import (
    DatabaseExecutionError,
    ExplainGateError,
    FreeQueryError,
    RejectionReason,
)
from app.modules.free_query.domain.interfaces import QueryAuditor, QueryExecutor
from app.modules.free_query.domain.policy import FreeQueryPolicy
from app.modules.free_query.domain.query_result import QueryResult

log = logging.getLogger(__name__)


class ExecuteFreeQueryUseCase:
    def __init__(
        self,
        executor: QueryExecutor,
        auditor: QueryAuditor,
        policy: FreeQueryPolicy,
    ) -> None:
        self._executor = executor
        self._auditor = auditor
        self._policy = policy

    async def execute(
        self,
        *,
        sql: str,
        conversation_id: UUID | None,
        user_question: str | None,
    ) -> QueryResult:
        started = time.perf_counter()
        normalized_sql = ""
        estimated: int | None = None
        try:
            normalized_sql = validate_and_normalize(sql, self._policy)
            estimated = await self._executor.estimate_rows(normalized_sql)
            if estimated > self._policy.max_estimated_rows:
                raise ExplainGateError(
                    f"La consulta es muy amplia: el planner estima "
                    f"~{estimated:,} filas (máximo {self._policy.max_estimated_rows:,}). "
                    "Afiná el filtro (por fecha, cliente, producto…) o "
                    "pedime un agregado (totales, conteos)."
                )
            columns, rows = await self._executor.execute_select(
                normalized_sql, max_rows=self._policy.max_rows
            )
            duration_ms = _elapsed_ms(started)
            await self._auditor.record(
                conversation_id=conversation_id,
                user_question=user_question,
                sql=normalized_sql,
                result=RejectionReason.OK,
                estimated_rows=estimated,
                returned_rows=len(rows),
                duration_ms=duration_ms,
                error_message=None,
            )
            truncated = len(rows) >= self._policy.max_rows and (
                estimated > self._policy.max_rows
            )
            return QueryResult(
                columns=columns,
                rows=rows,
                estimated_rows=estimated,
                returned_rows=len(rows),
                duration_ms=duration_ms,
                truncated=truncated,
                executed_sql=normalized_sql,
            )
        except FreeQueryError as e:
            await self._safe_audit(
                conversation_id,
                user_question,
                normalized_sql or sql,
                e.reason,
                estimated,
                None,
                _elapsed_ms(started),
                e.message,
            )
            raise
        except Exception as e:  # noqa: BLE001
            # Errores de Postgres (columna/tabla inexistente, sintaxis…)
            # los normalizamos a DatabaseExecutionError con un mensaje
            # ACCIONABLE: el LLM necesita saber qué columna/tabla falló
            # para poder consultar information_schema y autocorregirse.
            # Saneamos para no leak el SQL completo ni el traceback.
            db_msg = _extract_db_error_message(e)
            wrapped = DatabaseExecutionError(
                f"La BD rechazó la consulta: {db_msg}. "
                "Si el error es por una columna o tabla que no existe, "
                "ANTES de rendirte consultá `information_schema.columns` "
                "(con `table_schema` y `table_name` específicos + LIMIT 50) "
                "para descubrir los nombres reales, y reintentá una vez "
                "con los nombres correctos."
            )
            log.exception("free_query_unexpected_error sql=%r", sql[:200])
            await self._safe_audit(
                conversation_id,
                user_question,
                normalized_sql or sql,
                wrapped.reason,
                estimated,
                None,
                _elapsed_ms(started),
                str(e),
            )
            raise wrapped from e

    async def _safe_audit(
        self,
        conversation_id: UUID | None,
        user_question: str | None,
        sql: str,
        result: RejectionReason,
        estimated_rows: int | None,
        returned_rows: int | None,
        duration_ms: int,
        error_message: str | None,
    ) -> None:
        try:
            await self._auditor.record(
                conversation_id=conversation_id,
                user_question=user_question,
                sql=sql,
                result=result,
                estimated_rows=estimated_rows,
                returned_rows=returned_rows,
                duration_ms=duration_ms,
                error_message=error_message,
            )
        except Exception:
            log.exception("audit_record_failed conversation_id=%s", conversation_id)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


# SQLAlchemy concatena `[SQL: …] [parameters: …]` al `str(e)`. Los
# recortamos para no devolverle al LLM su propia query como "explicación"
# (la tiene en el turno anterior) y, sobre todo, para no leak parámetros.
_SQL_TAIL_RE = re.compile(r"\s*\[SQL:.*", flags=re.DOTALL)
_PARAMS_TAIL_RE = re.compile(r"\s*\[parameters:.*", flags=re.DOTALL)


def _extract_db_error_message(exc: BaseException) -> str:
    """Devuelve el mensaje primario del error de Postgres, sin SQL ni
    traceback.

    Si SQLAlchemy envolvió la excepción, preferimos `.orig` (el error
    crudo de asyncpg, que tiene textos claros tipo "no existe la columna
    «X»"). Si no hay `.orig`, usamos `str(exc)` y le quitamos los
    sufijos que SQLAlchemy agrega.
    """
    orig = getattr(exc, "orig", None)
    raw = str(orig) if orig is not None else str(exc)
    cleaned = _SQL_TAIL_RE.sub("", raw)
    cleaned = _PARAMS_TAIL_RE.sub("", cleaned)
    return cleaned.strip()[:300] or "error desconocido del motor de BD"


__all__ = ["ExecuteFreeQueryUseCase"]
