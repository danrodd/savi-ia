"""Tool MCP `consultar_libre` — SQL contra la BD del ERP, con defensas.

El LLM **sí** escribe SQL acá, pero pasa por:
- AST validator (sqlglot) que rechaza CTEs, UNION, LATERAL, OFFSET,
  SELECT *, subqueries muy anidadas, multi-statement; y obliga LIMIT.
- EXPLAIN gate que rechaza planes con > N filas estimadas.
- Cap post-ejecución de filas devueltas.
- Pool readonly forzado del ERP.
- Audit log (todo intento, ok o rechazo).

Lo usa para preguntas que no caen en `consultar_datos` (semantic layer)
ni en tools curadas. Es la última capa de la cascada.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from app.infrastructure.config import get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.modules.chat.infrastructure.llm.tools.result_sets import FULL_FETCH, make_recorder
from app.modules.erp_databases.infrastructure import get_erp_engine_for
from app.modules.free_query.application.formatter import format_result
from app.modules.free_query.application.use_cases import ExecuteFreeQueryUseCase
from app.modules.free_query.domain.errors import FreeQueryError
from app.modules.free_query.domain.policy import FreeQueryPolicy
from app.modules.free_query.infrastructure.sqlalchemy_query_auditor import (
    SqlAlchemyQueryAuditor,
)
from app.modules.free_query.infrastructure.sqlalchemy_query_executor import (
    SqlAlchemyQueryExecutor,
)

log = logging.getLogger(__name__)

# Columnas de contacto: marcan el conjunto para auditar su exportación.
_CONTACT_COLUMNS = frozenset(
    {"numeroidentificacion", "telefonofijo", "telefono", "celular", "email", "direccion"}
)

_SCHEMA_LOOKUP = re.compile(r"\binformation_schema\b", re.IGNORECASE)


def is_schema_lookup(sql: str) -> bool:
    """La consulta explora la estructura de la base, no datos del negocio.

    El modelo consulta `information_schema` para encontrar tablas y columnas.
    Ese resultado no se guarda como conjunto: si no, llega al chat como una
    tabla con nombres internos de la base.
    """
    return _SCHEMA_LOOKUP.search(sql) is not None


def build_consultar_libre_impl(
    conversation_id: UUID | None,
    erp_database_id: UUID | None = None,
):
    """Devuelve el handler de la tool, clausurando `conversation_id`.

    El MCP server arma una clausura nueva por turno (ver
    `build_savi_mcp_server`). Eso nos permite atar cada invocación al
    contexto del request sin estado global.
    """
    settings = get_settings()
    policy = FreeQueryPolicy(
        max_rows=settings.free_query_max_rows,
        fetch_rows=FULL_FETCH,
        max_estimated_rows=settings.free_query_max_estimated_rows,
        max_estimated_cost=settings.free_query_max_estimated_cost,
    )
    recorder = make_recorder(conversation_id)

    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        sql = args.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "El argumento 'sql' es obligatorio (string no vacío).",
                    }
                ],
                "isError": True,
            }
        user_question = args.get("pregunta_usuario")
        if user_question is not None and not isinstance(user_question, str):
            user_question = None

        use_case = ExecuteFreeQueryUseCase(
            executor=SqlAlchemyQueryExecutor(await get_erp_engine_for(erp_database_id)),
            auditor=SqlAlchemyQueryAuditor(get_agent_sessionmaker()),
            policy=policy,
        )
        try:
            result = await use_case.execute(
                sql=sql,
                conversation_id=conversation_id,
                user_question=user_question,
            )
        except FreeQueryError as e:
            return {
                "content": [{"type": "text", "text": e.message}],
                "isError": True,
            }
        kept = False
        kept_id: str | None = None
        if recorder is not None and len(result.rows) >= 2 and not is_schema_lookup(sql):
            title = (user_question or "Consulta del ERP").strip()[:150]
            personal = any(c.lower() in _CONTACT_COLUMNS for c in result.columns)
            try:
                kept_id = await recorder(
                    title,
                    result.columns,
                    {c: c for c in result.columns},
                    result.rows,
                    personal,
                    result.total_rows,
                )
                kept = True
            except Exception:  # noqa: BLE001 — guardar no puede tumbar la respuesta
                log.exception("result_set_record_failed tool=consultar_libre")
        text = format_result(result, shown=policy.max_rows, kept=kept, result_set_id=kept_id)
        return {"content": [{"type": "text", "text": text}]}

    return _impl
