from collections.abc import Sequence
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.application.permissions import (
    ensure_databases_exist,
    validate_visibility,
)
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    DocumentIndex,
    DocumentRepository,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentVisibility,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository


class UpdateCompanyDocumentUseCase:
    """Actualiza metadatos y permisos de acceso de un documento."""

    def __init__(
        self,
        repository: DocumentRepository,
        erp_repository: ErpDatabaseRepository,
        index: DocumentIndex | None = None,
    ) -> None:
        self._repository = repository
        self._erp_repository = erp_repository
        self._index = index

    async def execute(
        self,
        document_id: UUID,
        *,
        title: str | None = None,
        visibility: DocumentVisibility | None = None,
        modules: Sequence[ModuleCode] | None = None,
        all_databases: bool | None = None,
        database_ids: Sequence[UUID] | None = None,
    ) -> CompanyDocument:
        document = await self._repository.get_by_id(document_id)
        if document is None or document.is_deleted:
            raise CompanyDocumentNotFoundError(str(document_id))

        new_visibility = document.visibility if visibility is None else visibility
        new_modules = list(document.modules) if modules is None else list(modules)
        new_all_databases = document.all_databases if all_databases is None else all_databases
        new_database_ids = (
            list(document.database_ids) if database_ids is None else list(database_ids)
        )

        validate_visibility(new_visibility, new_modules, new_all_databases, new_database_ids)
        if not new_all_databases:
            await ensure_databases_exist(self._erp_repository, new_database_ids)

        if title is not None:
            document.title = title.strip()
        document.visibility = new_visibility
        document.modules = new_modules
        document.all_databases = new_all_databases
        # Con alcance "todas las bases" no se guardan filas de base: evita
        # que un cambio posterior a "bases específicas" herede una lista vieja.
        document.database_ids = [] if new_all_databases else new_database_ids

        if not await self._repository.update_access_metadata(document):
            raise CompanyDocumentNotFoundError(str(document_id))
        # Siempre, no solo si cambió el acceso: el título también viaja en
        # las citas que arma el índice.
        if self._index is not None:
            await self._index.update_metadata(document_id)
        return document
