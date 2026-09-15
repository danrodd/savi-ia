from dataclasses import dataclass
from uuid import UUID

from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.company_knowledge.domain.entities.document_access_view import (
    DocumentAccessView,
)
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)


@dataclass(frozen=True, slots=True)
class DocumentAccessContext:
    """Contexto de permisos del usuario en la base de la conversación."""

    erp_database_id: UUID
    modules: frozenset[ModuleCode]
    is_admin_in_database: bool
    is_savi_admin_login: bool


def can_read(document: DocumentAccessView, context: DocumentAccessContext) -> bool:
    """Política única de lectura. Deniega por defecto ante valores inesperados."""
    if document.status != DocumentStatus.READY or document.deleted:
        return False
    if not document.all_databases and context.erp_database_id not in document.database_ids:
        return False
    if document.visibility == DocumentVisibility.ALL:
        return True
    is_admin = context.is_admin_in_database or context.is_savi_admin_login
    if document.visibility == DocumentVisibility.ADMINS:
        return is_admin
    if document.visibility == DocumentVisibility.MODULES:
        return is_admin or not document.modules.isdisjoint(context.modules)
    return False
