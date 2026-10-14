"""Aplica las bases asignadas por Cloud a cada persona (M4).

Sin vinculación a Cloud, o sin reglas, no restringe: manda el ERP.
"""

from __future__ import annotations

from uuid import UUID

from app.modules.cloud_link.application.pseudonymizer import PseudonymizerProvider
from app.modules.cloud_link.domain.interfaces import CloudLinkRepository
from app.modules.erp_databases.domain.interfaces import DatabaseAccessPolicy


class CloudDatabaseAccessPolicy(DatabaseAccessPolicy):
    def __init__(
        self, repository: CloudLinkRepository, pseudonymizers: PseudonymizerProvider
    ) -> None:
        self._repository = repository
        self._pseudonymizers = pseudonymizers

    async def allowed_databases(
        self, *, user_id: int, identity_database_id: UUID
    ) -> frozenset[UUID] | None:
        state = await self._repository.get()
        rules = state.effective_policy.access if state.has_credentials else None
        if rules is None:
            return None
        user_ref = (await self._pseudonymizers.get()).user_ref(identity_database_id, user_id)
        return rules.allowed_for(user_ref)
