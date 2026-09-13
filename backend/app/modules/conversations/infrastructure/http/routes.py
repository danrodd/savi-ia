from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.auth.infrastructure.http import CurrentUserDep
from app.modules.conversations.application.dtos import CreateConversationDTO
from app.modules.conversations.application.requests import (
    CreateConversationRequest,
    RenameConversationRequest,
)
from app.modules.conversations.application.responses import (
    ConversationResponse,
    ConversationWithMessagesResponse,
)
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.http.dependencies import (
    CreateConversationUseCaseDep,
    DeleteConversationUseCaseDep,
    GetConversationWithMessagesUseCaseDep,
    ListConversationsUseCaseDep,
    RenameConversationUseCaseDep,
)
from app.modules.erp_databases.domain.exceptions import ErpDatabaseUnavailableError
from app.modules.erp_databases.infrastructure.http.dependencies import (
    ResolveModulesForDatabaseUseCaseDep,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _require_database(user: CurrentUserDep) -> UUID:
    """Base de identidad del usuario. Nunca `None`: el token no se
    puede decodificar sin ella."""
    assert user.erp_database_id is not None  # noqa: S101
    return user.erp_database_id


def _owner(user: CurrentUserDep) -> ConversationOwner:
    """Identidad completa del usuario autenticado.

    `erp_database_id` nunca es `None` acá: el token ya no se puede
    decodificar sin base (ver `_parse_subject`). El assert documenta esa
    garantía para el type checker.
    """
    assert user.erp_database_id is not None  # noqa: S101
    return ConversationOwner(
        user_id=user.id, erp_database_id=user.erp_database_id
    )


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: CreateConversationRequest,
    use_case: CreateConversationUseCaseDep,
    user: CurrentUserDep,
    access_resolver: ResolveModulesForDatabaseUseCaseDep,
) -> ConversationResponse:
    # El owner es SIEMPRE el usuario autenticado — no se acepta del body
    # para evitar impersonation.
    #
    # La base: la elegida en el body, o la de identidad si no se indicó.
    # Se valida el acceso con D3 —no se acepta a ciegas—: un usuario no
    # puede abrir una conversación contra un cliente donde no existe.
    database_id = request.erp_database_id or _require_database(user)
    access = await access_resolver.execute(user.login, database_id)
    if not access.has_access:
        raise ErpDatabaseUnavailableError(
            str(database_id),
            "No tenés acceso a esa base de datos, o no está disponible.",
        )

    dto = CreateConversationDTO(
        title=request.title,
        user_id=user.id,
        erp_database_id=database_id,
        owner_erp_database_id=_require_database(user),
    )
    result = await use_case.execute(dto)
    return ConversationResponse.from_dto(result)


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    use_case: ListConversationsUseCaseDep,
    user: CurrentUserDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ConversationResponse]:
    # Filtra siempre por el usuario autenticado.
    results = await use_case.execute(
        user.id,
        owner_erp_database_id=user.erp_database_id,
        limit=limit,
        offset=offset,
    )
    return [ConversationResponse.from_dto(r) for r in results]


@router.get("/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: UUID,
    use_case: GetConversationWithMessagesUseCaseDep,
    user: CurrentUserDep,
    include_superseded: bool = Query(
        default=False,
        description=(
            "Si true, incluye en `messages` las versiones anteriores de mensajes "
            "editados o regenerados (con `superseded_at`/`superseded_by_id` set). "
            "Default: solo el hilo activo."
        ),
    ),
) -> ConversationWithMessagesResponse:
    result = await use_case.execute(
        conversation_id,
        expected_owner=_owner(user),
        include_superseded=include_superseded,
    )
    return ConversationWithMessagesResponse.from_dto(result)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    request: RenameConversationRequest,
    use_case: RenameConversationUseCaseDep,
    user: CurrentUserDep,
) -> ConversationResponse:
    """Renombra la conversación y bloquea los autotítulos futuros
    (`title_locked=True`). Lo usa el botón de "Renombrar" del sidebar.
    """
    result = await use_case.execute(
        conversation_id, request.title, expected_owner=_owner(user)
    )
    return ConversationResponse.from_dto(result)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    use_case: DeleteConversationUseCaseDep,
    user: CurrentUserDep,
) -> None:
    """Soft delete idempotente: marca `deleted_at=now()` y deja de aparecer
    en listados / `GET /conversations/{id}`. Si ya estaba eliminada,
    devuelve 204 igual (idempotente). Si nunca existió o no pertenece al
    usuario, 404.

    No interrumpe turnos en curso: los writers independientes del módulo
    `chat` siguen insertando los mensajes pendientes contra la
    conversación, que quedan persistidos pero invisibles al usuario.
    """
    await use_case.execute(conversation_id, expected_owner=_owner(user))
