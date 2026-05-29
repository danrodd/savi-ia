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

from typing import Any
from uuid import UUID

from app.infrastructure.config import get_settings
from app.infrastructure.database import get_agent_sessionmaker
from app.infrastructure.database.pool import get_erp_engine
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


def build_consultar_libre_impl(conversation_id: UUID | None):
    """Devuelve el handler de la tool, clausurando `conversation_id`.

    El MCP server arma una clausura nueva por turno (ver
    `build_savi_mcp_server`). Eso nos permite atar cada invocación al
    contexto del request sin estado global.
    """
    settings = get_settings()
    policy = FreeQueryPolicy(
        max_rows=settings.free_query_max_rows,
        max_estimated_rows=settings.free_query_max_estimated_rows,
    )

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
            executor=SqlAlchemyQueryExecutor(get_erp_engine()),
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
        return {"content": [{"type": "text", "text": format_result(result)}]}

    return _impl
