"""Imágenes adjuntas en el turno del chat: validación, envío, edición,
regeneración y qué imágenes viajan al modelo.

Va contra SQLite real con el repositorio de transacciones cortas que usa el
endpoint; el runner, el writer de títulos y el LLM son dobles.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config import Settings
from app.infrastructure.database.base import Base
from app.modules.chat.application.requests import ChatAction, ChatRequest
from app.modules.chat.application.use_cases import ChatTurnUseCase
from app.modules.chat.application.use_cases.chat_turn import (
    _format_history_block,  # pyright: ignore[reportPrivateUsage]
    select_history_attachments,
)
from app.modules.chat.domain.entities import ChatEvent, DoneEvent, ImageInput, TextDeltaEvent
from app.modules.chat.domain.exceptions import TooManyChatImagesError
from app.modules.chat.domain.interfaces import (
    AssistantMessageWriter,
    ConversationTitleUpdater,
    LLMRunner,
)
from app.modules.chat.infrastructure.persistence import (
    ShortLivedConversationRepository,
    SqlAlchemyAssistantMessageWriter,
)
from app.modules.conversations.domain.entities import (
    ChatAttachment,
    Conversation,
    Message,
    MessageRole,
)
from app.modules.conversations.domain.exceptions import ChatAttachmentUnavailableError
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyChatAttachmentRepository,
    SqlAlchemyConversationRepository,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel

_DB = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_DB = UUID("33333333-3333-3333-3333-333333333333")
_OWNER = ConversationOwner(user_id=7, erp_database_id=_DB)


class _Runner:
    """Registra lo que recibe el modelo y responde algo fijo."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[ImageInput]]] = []

    async def stream_turn(
        self, prompt: str, *, images: Sequence[ImageInput] = (), **_: Any
    ) -> AsyncIterator[ChatEvent]:
        self.calls.append((prompt, list(images)))
        yield TextDeltaEvent(text="Veo la imagen.")
        yield DoneEvent()


class _Titles:
    def __init__(self) -> None:
        self.user_texts: list[str] = []

    async def update_from_user(self, conversation_id: UUID, text: str) -> str | None:
        self.user_texts.append(text)
        return None

    async def update_from_turn(
        self, conversation_id: UUID, user: str, assistant: str
    ) -> str | None:
        return None


class _World:
    def __init__(self, sm: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.sm = sm
        self.runner = _Runner()
        self.titles = _Titles()
        self.repository = ShortLivedConversationRepository(sm)
        self.conversation_id: UUID = uuid4()
        self.use_case = ChatTurnUseCase(
            self.repository,
            cast(LLMRunner, self.runner),
            cast(AssistantMessageWriter, SqlAlchemyAssistantMessageWriter(sm)),
            cast(ConversationTitleUpdater, self.titles),
            settings,
        )

    async def create_conversation(self) -> None:
        async with self.sm() as session:
            saved = await SqlAlchemyConversationRepository(session).save(
                Conversation(
                    id=self.conversation_id,
                    user_id=7,
                    erp_database_id=_DB,
                    owner_erp_database_id=_DB,
                )
            )
            await session.commit()
        self.conversation_id = saved.id

    async def upload(
        self, name: str, *, owner: ConversationOwner = _OWNER, data: bytes | None = None
    ) -> ChatAttachment:
        attachment = ChatAttachment(
            user_id=owner.user_id,
            owner_erp_database_id=owner.erp_database_id,
            mime="image/png",
            filename=name,
            size_bytes=10,
            width=4,
            height=4,
        )
        async with self.sm() as session:
            await SqlAlchemyChatAttachmentRepository(session).add(
                attachment, data if data is not None else f"bytes-de-{name}".encode()
            )
            await session.commit()
        return attachment

    async def turn(
        self,
        action: ChatAction = ChatAction.SEND,
        message: str | None = None,
        attachments: Sequence[ChatAttachment] = (),
    ) -> list[ChatEvent]:
        ids = [a.id for a in attachments]
        await self.use_case.validate(
            self.conversation_id, action, expected_owner=_OWNER, attachment_ids=ids
        )
        events = [
            event
            async for event in self.use_case.execute(
                self.conversation_id, action, message, attachment_ids=ids
            )
        ]
        await asyncio.sleep(0.05)  # el writer del assistant corre en una tarea independiente
        return events

    async def messages(self, *, include_superseded: bool = False) -> list[Message]:
        return await self.repository.list_messages(
            self.conversation_id, include_superseded=include_superseded
        )

    async def content_of(self, attachment_id: UUID) -> bytes | None:
        async with self.sm() as session:
            return await SqlAlchemyChatAttachmentRepository(session).get_content(attachment_id)


@pytest_asyncio.fixture
async def sessionmaker_(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'turno.db').as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001 - firma del evento
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        for database_id, code in ((_DB, "DUENO"), (_OTHER_DB, "OTRO")):
            s.add(
                ErpDatabaseModel(
                    id=database_id,
                    code=code,
                    name=f"Cliente {code}",
                    host="localhost",
                    port=5432,
                    database=f"erp_{code.lower()}",
                    username="postgres",
                    password_encrypted="cifrado",
                )
            )
        await s.commit()
    yield factory
    await engine.dispose()


async def _world(sm: async_sessionmaker[AsyncSession], **settings: Any) -> _World:
    world = _World(sm, Settings(title_phase2_timeout_s=0.01, **settings))
    await world.create_conversation()
    return world


# ── ChatRequest ───────────────────────────────────────────────────────────


def test_an_image_only_message_is_a_valid_request() -> None:
    request = ChatRequest(conversation_id=uuid4(), attachment_ids=[uuid4()])

    assert request.message is None
    assert len(request.attachment_ids) == 1


@pytest.mark.parametrize("action", [ChatAction.SEND, ChatAction.EDIT_LAST])
def test_a_blank_message_without_images_is_still_rejected(action: ChatAction) -> None:
    with pytest.raises(PydanticValidationError):
        ChatRequest(conversation_id=uuid4(), action=action, message="   ")


def test_regenerate_needs_neither_message_nor_images() -> None:
    ChatRequest(conversation_id=uuid4(), action=ChatAction.REGENERATE)


def test_repeated_attachment_ids_count_once() -> None:
    one = uuid4()

    request = ChatRequest(conversation_id=uuid4(), message="x", attachment_ids=[one, one])

    assert request.attachment_ids == [one]


# ── validate ──────────────────────────────────────────────────────────────


async def test_more_images_than_the_limit_are_rejected(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_, chat_images_per_message=2)
    attachments = [await world.upload(f"{i}.png") for i in range(3)]

    with pytest.raises(TooManyChatImagesError) as excinfo:
        await world.use_case.validate(
            world.conversation_id,
            ChatAction.SEND,
            expected_owner=_OWNER,
            attachment_ids=[a.id for a in attachments],
        )

    assert "2" in str(excinfo.value)


async def test_the_limit_itself_is_accepted(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_, chat_images_per_message=2)
    attachments = [await world.upload(f"{i}.png") for i in range(2)]

    await world.turn(attachments=attachments)

    assert len((await world.messages())[0].attachments) == 2


@pytest.mark.parametrize(
    "stranger",
    [
        ConversationOwner(user_id=8, erp_database_id=_DB),  # otro usuario
        ConversationOwner(user_id=7, erp_database_id=_OTHER_DB),  # mismo id, otro cliente
    ],
)
async def test_someone_elses_image_is_rejected_like_a_missing_one(
    sessionmaker_: async_sessionmaker[AsyncSession], stranger: ConversationOwner
) -> None:
    world = await _world(sessionmaker_)
    foreign = await world.upload("ajena.png", owner=stranger)

    async def attempt(ids: list[UUID]) -> str:
        with pytest.raises(ChatAttachmentUnavailableError) as excinfo:
            await world.use_case.validate(
                world.conversation_id, ChatAction.SEND, expected_owner=_OWNER, attachment_ids=ids
            )
        return str(excinfo.value)

    assert await attempt([foreign.id]) == await attempt([uuid4()])


async def test_an_image_already_sent_in_a_message_cannot_be_reused_on_send(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    used = await world.upload("usada.png")
    await world.turn(message="mira", attachments=[used])

    with pytest.raises(ChatAttachmentUnavailableError):
        await world.use_case.validate(
            world.conversation_id,
            ChatAction.SEND,
            expected_owner=_OWNER,
            attachment_ids=[used.id],
        )


async def test_edit_last_accepts_the_replaced_messages_images_but_not_older_ones(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    first = await world.upload("primera.png")
    second = await world.upload("segunda.png")
    await world.turn(message="uno", attachments=[first])
    await world.turn(message="dos", attachments=[second])
    messages = await world.messages()
    first_message_attachment = messages[0].attachments[0]
    second_message_attachment = messages[2].attachments[0]

    await world.use_case.validate(
        world.conversation_id,
        ChatAction.EDIT_LAST,
        expected_owner=_OWNER,
        attachment_ids=[second_message_attachment.id],
    )
    with pytest.raises(ChatAttachmentUnavailableError):
        await world.use_case.validate(
            world.conversation_id,
            ChatAction.EDIT_LAST,
            expected_owner=_OWNER,
            attachment_ids=[first_message_attachment.id],
        )


# ── send ──────────────────────────────────────────────────────────────────


async def test_an_image_only_send_links_the_image_and_reaches_the_model(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    photo = await world.upload("factura.png", data=b"PIXELES")

    events = await world.turn(attachments=[photo])

    assert any(isinstance(e, DoneEvent) for e in events)
    user_message, assistant_message = await world.messages()
    assert (user_message.role, user_message.content) == (MessageRole.USER, "")
    assert [(a.id, a.message_id) for a in user_message.attachments] == [(photo.id, user_message.id)]
    assert assistant_message.role == MessageRole.ASSISTANT
    prompt, images = world.runner.calls[0]
    assert "sin texto" in prompt
    assert images == [
        ImageInput(
            mime="image/png", data=b"PIXELES", filename="factura.png", from_current_turn=True
        )
    ]


async def test_a_text_only_send_sends_no_images_and_leaves_the_prompt_untouched(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)

    await world.turn(message="  hola  ")

    assert world.runner.calls == [("hola", [])]


async def test_the_auto_title_never_gets_empty_text(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    photo = await world.upload("a.png")

    await world.turn(attachments=[photo])

    assert world.titles.user_texts == ["Imagen adjunta"]


async def test_the_title_uses_the_text_when_there_is_one(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    photo = await world.upload("a.png")

    await world.turn(message="¿qué código aparece?", attachments=[photo])

    assert world.titles.user_texts == ["¿qué código aparece?"]


async def test_a_race_on_the_image_leaves_no_half_written_message(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    """Si entre `validate` y el envío la imagen se la quedó otro mensaje, el
    envío falla entero: no queda un mensaje sin su imagen."""
    world = await _world(sessionmaker_)
    photo = await world.upload("a.png")
    other = _World(sessionmaker_, Settings())
    other.conversation_id = world.conversation_id
    await other.turn(message="gané yo", attachments=[photo])
    before = len(await world.messages())

    with pytest.raises(ChatAttachmentUnavailableError):
        async for _ in world.use_case.execute(
            world.conversation_id, ChatAction.SEND, "perdí", attachment_ids=[photo.id]
        ):
            pass

    assert len(await world.messages()) == before


# ── historial ─────────────────────────────────────────────────────────────


def _message(role: MessageRole, text: str, *names: str, active: bool = True) -> Message:
    from datetime import UTC, datetime

    return Message(
        role=role,
        content=text,
        attachments=[
            ChatAttachment(
                user_id=1,
                owner_erp_database_id=_DB,
                mime="image/png",
                filename=name,
                size_bytes=1,
                width=1,
                height=1,
            )
            for name in names
        ],
        superseded_at=None if active else datetime.now(UTC),
    )


def test_history_text_marks_each_attached_image() -> None:
    history = [
        _message(MessageRole.USER, "mirá esto", "uno.png", "dos.png"),
        _message(MessageRole.ASSISTANT, "listo"),
        _message(MessageRole.USER, "", "solo.png"),
    ]

    block = _format_history_block(history)

    assert "Usuario: mirá esto\n[imagen adjunta: uno.png]\n[imagen adjunta: dos.png]" in block
    assert "Usuario: [imagen adjunta: solo.png]" in block


def test_history_images_are_newest_first_and_capped() -> None:
    history = [
        _message(MessageRole.USER, "a", "a1.png"),
        _message(MessageRole.ASSISTANT, "ok"),
        _message(MessageRole.USER, "b", "b1.png", "b2.png"),
        _message(MessageRole.ASSISTANT, "ok"),
        _message(MessageRole.USER, "c", "c1.png"),
    ]

    names = [a.filename for a in select_history_attachments(history, 3)]

    assert names == ["c1.png", "b1.png", "b2.png"]
    assert select_history_attachments(history, 0) == []


def test_history_images_skip_replaced_messages() -> None:
    history = [
        _message(MessageRole.USER, "viejo", "viejo.png", active=False),
        _message(MessageRole.USER, "nuevo", "nuevo.png"),
    ]

    assert [a.filename for a in select_history_attachments(history, 4)] == ["nuevo.png"]


async def test_previous_images_are_resent_and_marked_in_the_history_text(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    photo = await world.upload("fondo.png", data=b"FONDO")
    await world.turn(message="mirá", attachments=[photo])

    await world.turn(message="¿de qué color es el fondo?")

    prompt, images = world.runner.calls[1]
    assert "[imagen adjunta: fondo.png]" in prompt
    assert images == [
        ImageInput(mime="image/png", data=b"FONDO", filename="fondo.png", from_current_turn=False)
    ]


async def test_current_images_always_go_and_previous_ones_are_capped_newest_first(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_, chat_history_images_max=2)
    for name in ("m1.png", "m2.png", "m3.png"):
        await world.turn(message=name, attachments=[await world.upload(name)])
    current = [await world.upload("actual1.png"), await world.upload("actual2.png")]

    await world.turn(message="¿y ahora?", attachments=current)

    _, images = world.runner.calls[-1]
    assert [(i.filename, i.from_current_turn) for i in images] == [
        ("m3.png", False),
        ("m2.png", False),
        ("actual1.png", True),
        ("actual2.png", True),
    ]


async def test_zero_history_images_still_sends_the_current_ones(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_, chat_history_images_max=0)
    await world.turn(message="antes", attachments=[await world.upload("vieja.png")])

    await world.turn(message="ahora", attachments=[await world.upload("nueva.png")])

    assert [i.filename for i in world.runner.calls[-1][1]] == ["nueva.png"]


# ── edit_last ─────────────────────────────────────────────────────────────


async def test_edit_last_copies_kept_images_and_the_old_version_keeps_its_own(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    kept = await world.upload("conservada.png", data=b"KEEP")
    await world.turn(message="versión 1", attachments=[kept])
    added = await world.upload("nueva.png", data=b"NEW")

    await world.turn(ChatAction.EDIT_LAST, "versión 2", attachments=[kept, added])

    active = await world.messages()
    everything = await world.messages(include_superseded=True)
    old_user = next(m for m in everything if m.content == "versión 1")
    new_user = next(m for m in active if m.role == MessageRole.USER)
    assert old_user.superseded_at is not None
    # La versión anterior conserva su imagen original, con sus bytes.
    assert [a.id for a in old_user.attachments] == [kept.id]
    assert await world.content_of(kept.id) == b"KEEP"
    # La nueva tiene una COPIA de la conservada (otra fila) y la recién subida.
    by_name = {a.filename: a for a in new_user.attachments}
    assert set(by_name) == {"conservada.png", "nueva.png"}
    assert by_name["conservada.png"].id != kept.id
    assert by_name["conservada.png"].message_id == new_user.id
    assert await world.content_of(by_name["conservada.png"].id) == b"KEEP"
    assert by_name["nueva.png"].id == added.id
    # Ambas llegan al modelo como imágenes del turno actual.
    _, images = world.runner.calls[-1]
    assert {(i.filename, i.data, i.from_current_turn) for i in images} == {
        ("conservada.png", b"KEEP", True),
        ("nueva.png", b"NEW", True),
    }


async def test_edit_last_without_ids_drops_the_images_from_the_new_version_only(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    photo = await world.upload("foto.png")
    await world.turn(message="con foto", attachments=[photo])

    await world.turn(ChatAction.EDIT_LAST, "sin foto")

    new_user = next(m for m in await world.messages() if m.role == MessageRole.USER)
    old_user = next(
        m for m in await world.messages(include_superseded=True) if m.content == "con foto"
    )
    assert new_user.attachments == []
    assert [a.id for a in old_user.attachments] == [photo.id]
    assert world.runner.calls[-1][1] == []


# ── regenerate ────────────────────────────────────────────────────────────


async def test_regenerate_reuses_the_last_messages_images_without_creating_new_ones(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    world = await _world(sessionmaker_)
    photo = await world.upload("foto.png", data=b"FOTO")
    await world.turn(message="mirá", attachments=[photo])
    first_images = world.runner.calls[0][1]

    await world.turn(ChatAction.REGENERATE)

    assert world.runner.calls[1][1] == first_images
    assert all(i.from_current_turn for i in world.runner.calls[1][1])
    users = [m for m in await world.messages() if m.role == MessageRole.USER]
    assert [[a.id for a in m.attachments] for m in users] == [[photo.id]]
    assert world.titles.user_texts == ["mirá"]  # regenerate no vuelve a titular
