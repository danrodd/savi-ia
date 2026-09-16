"""Los tres endpoints que aparecen cuando el turno deja de ser la conexión.

`GET /chat/activo`, `GET /chat/stream` y `POST /chat/detener` reciben un
`conversation_id` del cliente: sin chequeo de dueño, cualquiera con una sesión
válida podría espiar o cortar la respuesta de otro pasando el UUID. Se prueba
esa frontera, no el registro de turnos (eso vive en
`test_turn_concurrency.py`).

Se llama a los handlers directo, sin ASGI: los tipos `XDep` son solo
`Annotated[X, Depends(...)]` y llamar la función a mano los ignora.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.chat.infrastructure.http.routes import detener, reenganchar, turno_activo
from app.modules.chat.infrastructure.http.turn_registry import RunningTurn, get_turn_registry
from app.modules.conversations.domain.entities import Conversation
from app.modules.conversations.domain.interfaces import ConversationRepository
from app.shared.exceptions import NotFoundError

_OWNER_DB = uuid4()
_OTHER_DB = uuid4()


class _StubConversations:
    """Solo `get_by_id`: es lo único que el chequeo de dueño necesita."""

    def __init__(self, conversation: Conversation | None) -> None:
        self._conversation = conversation

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return self._conversation


def _user(erp_database_id: UUID = _OWNER_DB, user_id: int = 1) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id,
        login="ADMIN",
        full_name="Administrador",
        is_admin=True,
        is_active=True,
        erp_database_id=erp_database_id,
    )


def _conversation(conversation_id: UUID) -> Conversation:
    return Conversation(
        id=conversation_id,
        user_id=1,
        # La base consultada es OTRA que la del dueño: así se nota si el
        # chequeo mira la columna equivocada.
        erp_database_id=_OTHER_DB,
        owner_erp_database_id=_OWNER_DB,
    )


def _repo(conversation: Conversation | None) -> ConversationRepository:
    return cast(ConversationRepository, _StubConversations(conversation))


@pytest.fixture(autouse=True)
def _limpio():
    get_turn_registry().reset_for_tests()
    yield
    get_turn_registry().reset_for_tests()


async def test_activo_says_no_when_nothing_is_running() -> None:
    cid = uuid4()

    resultado = await turno_activo(cid, _user(), _repo(_conversation(cid)))

    assert resultado == {"activo": False}


async def test_activo_says_yes_while_the_turn_runs() -> None:
    cid = uuid4()
    registro = get_turn_registry()
    registro._turns[cid] = RunningTurn(conversation_id=cid)  # pyright: ignore[reportPrivateUsage]

    resultado = await turno_activo(cid, _user(), _repo(_conversation(cid)))

    assert resultado == {"activo": True}


async def test_activo_hides_someone_elses_conversation() -> None:
    """404 y no 403: distinguir "no existe" de "no es tuya" confirma UUIDs."""
    cid = uuid4()

    with pytest.raises(NotFoundError):
        await turno_activo(cid, _user(user_id=999), _repo(_conversation(cid)))


async def test_activo_rejects_a_conversation_from_another_database() -> None:
    cid = uuid4()

    with pytest.raises(NotFoundError):
        await turno_activo(cid, _user(erp_database_id=uuid4()), _repo(_conversation(cid)))


async def test_stream_404s_when_there_is_no_turn() -> None:
    cid = uuid4()

    with pytest.raises(NotFoundError):
        await reenganchar(cid, _user(), _repo(_conversation(cid)))


async def test_stream_replays_the_running_turn() -> None:
    cid = uuid4()
    get_turn_registry()._turns[cid] = RunningTurn(  # pyright: ignore[reportPrivateUsage]
        conversation_id=cid
    )

    response = await reenganchar(cid, _user(), _repo(_conversation(cid)))

    assert response.media_type == "text/event-stream"


async def test_detener_is_idempotent() -> None:
    """Sin turno en curso responde igual: el botón no puede quedar trabado."""
    cid = uuid4()

    assert await detener(cid, _user(), _repo(_conversation(cid))) is None


async def test_detener_hides_someone_elses_conversation() -> None:
    cid = uuid4()

    with pytest.raises(NotFoundError):
        await detener(cid, _user(user_id=999), _repo(_conversation(cid)))


async def test_a_missing_conversation_is_a_404_too() -> None:
    with pytest.raises(NotFoundError):
        await turno_activo(uuid4(), _user(), _repo(None))
