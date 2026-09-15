from collections.abc import Sequence
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentInvalidError,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentVisibility,
)
from app.modules.erp_databases.domain.interfaces import ErpDatabaseRepository


def validate_visibility(
    visibility: DocumentVisibility,
    modules: Sequence[ModuleCode],
    all_databases: bool,
    database_ids: Sequence[UUID],
) -> None:
    """Valida la coherencia entre visibilidad, módulos y bases del documento."""
    if visibility == DocumentVisibility.MODULES and not modules:
        raise CompanyDocumentInvalidError("La visibilidad por módulos requiere al menos un módulo.")
    if visibility != DocumentVisibility.MODULES and modules:
        raise CompanyDocumentInvalidError("Solo la visibilidad por módulos admite módulos.")
    if not all_databases and not database_ids:
        raise CompanyDocumentInvalidError(
            "Debe indicar al menos una base cuando el documento no aplica a todas."
        )


async def ensure_databases_exist(
    repository: ErpDatabaseRepository, database_ids: Sequence[UUID]
) -> None:
    """Verifica que cada base exista y sea utilizable."""
    for database_id in database_ids:
        database = await repository.get_by_id(database_id)
        if database is None or not database.is_usable:
            raise CompanyDocumentInvalidError(f"Base inexistente: {database_id}")
