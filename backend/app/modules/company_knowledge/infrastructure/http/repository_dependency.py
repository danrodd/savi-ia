"""Dependencia del repositorio de documentos, sin importar otros módulos HTTP.

Vive aparte de `dependencies.py` para que `conversations` pueda usarla sin
cerrar un ciclo de imports (`dependencies.py` importa DI de `conversations`).
"""

from typing import Annotated

from fastapi import Depends

from app.infrastructure.database import get_agent_sessionmaker
from app.modules.company_knowledge.domain.interfaces import DocumentRepository
from app.modules.company_knowledge.infrastructure.persistence.sqlalchemy_document_repository import (  # noqa: E501
    SqlAlchemyDocumentRepository,
)
from app.modules.company_knowledge.infrastructure.provider import (
    get_company_knowledge_runtime,
)


def get_document_repository() -> DocumentRepository:
    runtime = get_company_knowledge_runtime()
    if runtime is not None:
        return runtime.repository
    return SqlAlchemyDocumentRepository(get_agent_sessionmaker())


DocumentRepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]
