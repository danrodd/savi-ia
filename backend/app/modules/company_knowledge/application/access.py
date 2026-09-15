from collections.abc import Collection
from uuid import UUID

from app.modules.auth.application.use_cases import DatabaseAccess
from app.modules.company_knowledge.domain.services import DocumentAccessContext


def build_access_context(
    access: DatabaseAccess,
    *,
    erp_database_id: UUID,
    login: str,
    savi_admin_logins: Collection[str],
) -> DocumentAccessContext:
    """Contexto de permisos para documentos en la base de la conversación.

    Siempre desde el `DatabaseAccess` resuelto para ESA base (D3): módulos e
    `is_admin` de la base consultada, nunca los de la base de identidad.
    """
    return DocumentAccessContext(
        erp_database_id=erp_database_id,
        modules=frozenset(access.modules),
        is_admin_in_database=access.is_admin_in_database,
        is_savi_admin_login=login.strip().upper() in savi_admin_logins,
    )
