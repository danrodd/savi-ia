"""Casos de uso que exponen documentos a usuarios: descarga, disponibilidad
de fuentes y prueba de búsqueda.

Los tres pasan por la MISMA política (`can_read`) evaluada contra la base
de la conversación. Todo rechazo de descarga es "no existe" (404): no se
confirma la existencia de un documento a quien no puede verlo.
"""

import logging
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.auth.application.use_cases import ResolveModulesForDatabaseUseCase
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.company_knowledge.application.access import build_access_context
from app.modules.company_knowledge.domain.entities.company_document import (
    CompanyDocument,
)
from app.modules.company_knowledge.domain.entities.document_access_view import (
    DocumentAccessView,
)
from app.modules.company_knowledge.domain.exceptions import (
    CompanyDocumentNotFoundError,
)
from app.modules.company_knowledge.domain.interfaces import (
    ChunkHit,
    DocumentIndex,
    DocumentRepository,
    SourceAvailability,
    SourceAvailabilityResolver,
)
from app.modules.company_knowledge.domain.services import DocumentAccessContext, can_read
from app.modules.company_knowledge.domain.value_objects.visibility import (
    DocumentStatus,
    DocumentVisibility,
)
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.modules.conversations.domain.value_objects import ConversationOwner

logger = logging.getLogger(__name__)


def _view(document: CompanyDocument) -> DocumentAccessView:
    return DocumentAccessView.from_document(document, frozenset(document.database_ids))


class RepositorySourceAvailabilityResolver(SourceAvailabilityResolver):
    """Disponibilidad de fuentes citadas, para quien consulta el historial."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def resolve(
        self, document_ids: Sequence[UUID], ctx: DocumentAccessContext
    ) -> dict[UUID, SourceAvailability]:
        unique = list(dict.fromkeys(document_ids))
        documents = {doc.id: doc for doc in await self._repository.get_by_ids(unique)}
        result: dict[UUID, SourceAvailability] = {}
        for document_id in unique:
            document = documents.get(document_id)
            if document is None or document.is_deleted:
                result[document_id] = SourceAvailability(available=False, reason="deleted")
            elif document.status != DocumentStatus.READY:
                # Reemplazado y en reproceso: vuelve cuando termine.
                result[document_id] = SourceAvailability(available=False, reason="processing")
            elif not can_read(_view(document), ctx):
                result[document_id] = SourceAvailability(available=False, reason="no_access")
            else:
                result[document_id] = SourceAvailability(available=True)
        return result


class DownloadCompanyDocumentUseCase:
    def __init__(
        self,
        *,
        repository: DocumentRepository,
        conversations: ConversationRepository,
        access_resolver: ResolveModulesForDatabaseUseCase,
        savi_admin_logins: Collection[str],
    ) -> None:
        self._repository = repository
        self._conversations = conversations
        self._access_resolver = access_resolver
        self._savi_admin_logins = savi_admin_logins

    async def execute(
        self, document_id: UUID, conversation_id: UUID, user: AuthenticatedUser
    ) -> tuple[CompanyDocument, bytes]:
        not_found = CompanyDocumentNotFoundError(str(document_id))
        if user.erp_database_id is None:
            raise not_found

        # 1. La conversación es del usuario.
        conversation = await self._conversations.get_by_id(conversation_id)
        owner = ConversationOwner(user_id=user.id, erp_database_id=user.erp_database_id)
        if (
            conversation is None
            or conversation.is_deleted
            or conversation.erp_database_id is None
            or not owner.owns(conversation.user_id, conversation.owner_erp_database_id)
        ):
            raise not_found

        # 2. Algún mensaje activo cita el documento: una conversación propia
        # no sirve de llave para descargar cualquier documento.
        messages = await self._conversations.list_messages(conversation_id)
        if not any(
            source.document_id == document_id for message in messages for source in message.sources
        ):
            raise not_found

        # 3. La política, con los permisos del usuario en ESA base.
        access = await self._access_resolver.execute(
            user.login, conversation.erp_database_id, identity=user
        )
        if not access.has_access:
            raise not_found
        ctx = build_access_context(
            access,
            erp_database_id=conversation.erp_database_id,
            login=user.login,
            savi_admin_logins=self._savi_admin_logins,
        )
        document = await self._repository.get_by_id(document_id)
        if document is None or not can_read(_view(document), ctx):
            raise not_found
        content = await self._repository.get_blob(document_id)
        if content is None:
            raise not_found
        return document, content


@dataclass(frozen=True, slots=True)
class SearchTestContext:
    login: str
    has_access: bool
    modules: tuple[str, ...]
    is_admin: bool


@dataclass(frozen=True, slots=True)
class ExcludedDocument:
    document_id: UUID
    title: str
    reason: str


@dataclass(frozen=True, slots=True)
class SearchTestResult:
    context: SearchTestContext
    results: list[ChunkHit]
    excluded_documents: list[ExcludedDocument]


class TestDocumentSearchUseCase:
    """Prueba de búsqueda del administrador, opcionalmente como otro usuario.

    Usa el mismo `DocumentIndex.search` que el chat: una lógica paralela
    podría dar "bien" en la prueba y filtrar distinto en producción.
    """

    __test__ = False  # que pytest no lo tome por una clase de tests

    def __init__(
        self,
        *,
        index: DocumentIndex | None,
        repository: DocumentRepository,
        access_resolver: ResolveModulesForDatabaseUseCase,
        savi_admin_logins: Collection[str],
        embedding_model: str,
        limit: int,
    ) -> None:
        self._index = index
        self._repository = repository
        self._access_resolver = access_resolver
        self._savi_admin_logins = savi_admin_logins
        self._embedding_model = embedding_model
        self._limit = limit

    async def execute(
        self, *, query: str, erp_database_id: UUID, login: str, admin_login: str
    ) -> SearchTestResult:
        access = await self._access_resolver.execute(login, erp_database_id)
        test_context = SearchTestContext(
            login=login,
            has_access=access.has_access,
            modules=tuple(sorted(module.value for module in access.modules)),
            is_admin=access.is_admin_in_database,
        )
        logger.info(
            "company_docs_search_test admin=%s as_login=%s database=%s",
            admin_login,
            login,
            erp_database_id,
        )
        if not access.has_access:
            return SearchTestResult(context=test_context, results=[], excluded_documents=[])

        ctx = build_access_context(
            access,
            erp_database_id=erp_database_id,
            login=login,
            savi_admin_logins=self._savi_admin_logins,
        )
        results = (
            await self._index.search(query, ctx, limit=self._limit)
            if self._index is not None
            else []
        )
        excluded: list[ExcludedDocument] = []
        for document in await self._repository.list_ready_for_index(self._embedding_model):
            reason = _exclusion_reason(_view(document), ctx)
            if reason is not None:
                excluded.append(ExcludedDocument(document.id, document.title, reason))
        return SearchTestResult(context=test_context, results=results, excluded_documents=excluded)


def _exclusion_reason(view: DocumentAccessView, ctx: DocumentAccessContext) -> str | None:
    if can_read(view, ctx):
        return None
    if not view.all_databases and ctx.erp_database_id not in view.database_ids:
        return "database_scope"
    if view.visibility == DocumentVisibility.ADMINS:
        return "visibility_admins"
    if view.visibility == DocumentVisibility.MODULES:
        return "visibility_modules"
    return "not_available"
