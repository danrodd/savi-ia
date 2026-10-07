"""Imágenes adjuntas del chat: subida, procesamiento, descarga y listado.

Se prueba contra SQLite real (mismo metadata que producción) y con Pillow
real: lo que importa es qué queda guardado y quién lo puede leer, no cómo
se llaman los métodos.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main as main_module
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_agent_session
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import get_current_user
from app.modules.conversations.application.mappers import ConversationMapper
from app.modules.conversations.application.responses import MessageResponse
from app.modules.conversations.application.use_cases import (
    GetChatAttachmentUseCase,
    UploadChatAttachmentUseCase,
)
from app.modules.conversations.application.use_cases.upload_chat_attachment import (
    sanitize_attachment_filename,
)
from app.modules.conversations.domain.entities import (
    ChatAttachment,
    Conversation,
    Message,
    MessageRole,
)
from app.modules.conversations.domain.exceptions import (
    ChatAttachmentNotFoundError,
    ChatAttachmentTooLargeError,
    InvalidChatAttachmentError,
)
from app.modules.conversations.domain.value_objects import ConversationOwner
from app.modules.conversations.infrastructure.imaging import PillowImageProcessor
from app.modules.conversations.infrastructure.persistence.repositories import (
    SqlAlchemyChatAttachmentRepository,
    SqlAlchemyConversationRepository,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel

_OWNER_DB = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_DB = UUID("33333333-3333-3333-3333-333333333333")
_OWNER = ConversationOwner(user_id=7, erp_database_id=_OWNER_DB)


def _erp_database(database_id: UUID, code: str) -> ErpDatabaseModel:
    return ErpDatabaseModel(
        id=database_id,
        code=code,
        name=f"Cliente {code}",
        host="localhost",
        port=5432,
        database=f"erp_{code.lower()}",
        username="postgres",
        password_encrypted="cifrado",
    )


@pytest_asyncio.fixture
async def sessionmaker_(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'adjuntos.db').as_posix()}")

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
        s.add(_erp_database(_OWNER_DB, "DUENO"))
        s.add(_erp_database(_OTHER_DB, "OTRO"))
        await s.commit()
    yield factory
    await engine.dispose()


def _sqlite_time(moment: datetime) -> str:
    """Mismo formato con el que SQLAlchemy guarda los datetime en SQLite."""
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _image(
    fmt: str = "PNG",
    size: tuple[int, int] = (64, 32),
    mode: str = "RGB",
    **save_kwargs: object,
) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, "navy").save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


async def _upload(
    sm: async_sessionmaker[AsyncSession],
    content: bytes,
    *,
    filename: str | None = "foto.png",
    owner: ConversationOwner = _OWNER,
    settings: Settings | None = None,
) -> ChatAttachment:
    async with sm() as session:
        use_case = UploadChatAttachmentUseCase(
            SqlAlchemyChatAttachmentRepository(session),
            PillowImageProcessor(),
            settings or Settings(),
        )
        attachment = await use_case.execute(owner=owner, filename=filename, content=content)
        await session.commit()
    return attachment


# ── Subida ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fmt", "mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
async def test_accepts_png_jpeg_and_webp_and_returns_metadata(
    sessionmaker_: async_sessionmaker[AsyncSession], fmt: str, mime: str
) -> None:
    raw = _image(fmt, (120, 80))

    attachment = await _upload(sessionmaker_, raw, filename="captura.png")

    assert attachment.mime == mime
    assert (attachment.width, attachment.height) == (120, 80)
    assert attachment.filename == "captura.png"
    assert attachment.size_bytes > 0
    assert (attachment.user_id, attachment.owner_erp_database_id) == (7, _OWNER_DB)
    assert attachment.message_id is None


async def test_rejects_a_text_file_disguised_as_png(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(InvalidChatAttachmentError):
        await _upload(sessionmaker_, b"esto no es una imagen", filename="falso.png")


async def test_rejects_an_unsupported_image_format_even_if_pillow_can_read_it(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(InvalidChatAttachmentError):
        await _upload(sessionmaker_, _image("BMP"), filename="mapa.png")


async def test_rejects_an_empty_file(sessionmaker_: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(InvalidChatAttachmentError):
        await _upload(sessionmaker_, b"")


async def test_rejects_a_file_over_the_size_limit(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(chat_image_max_mb=1)

    with pytest.raises(ChatAttachmentTooLargeError) as excinfo:
        await _upload(sessionmaker_, b"0" * (1024 * 1024 + 1), settings=settings)

    assert excinfo.value.limit_mb == 1
    assert "1 MB" in str(excinfo.value)


async def test_downscales_a_wide_image_to_the_max_side(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    attachment = await _upload(sessionmaker_, _image("PNG", (4000, 1000)))

    assert (attachment.width, attachment.height) == (2048, 512)
    async with sessionmaker_() as session:
        content = await SqlAlchemyChatAttachmentRepository(session).get_content(attachment.id)
    assert content is not None
    with Image.open(io.BytesIO(content)) as stored:
        assert stored.size == (2048, 512)
    assert attachment.size_bytes == len(content)


async def test_does_not_upscale_a_small_image(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    attachment = await _upload(sessionmaker_, _image("JPEG", (300, 200)))

    assert (attachment.width, attachment.height) == (300, 200)


async def test_a_gif_keeps_only_the_first_frame_as_png(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    buffer = io.BytesIO()
    first = Image.new("RGB", (50, 40), "red")
    first.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (50, 40), "blue")],
        duration=100,
    )

    attachment = await _upload(sessionmaker_, buffer.getvalue(), filename="anim.gif")

    assert attachment.mime == "image/png"
    async with sessionmaker_() as session:
        content = await SqlAlchemyChatAttachmentRepository(session).get_content(attachment.id)
    assert content is not None
    with Image.open(io.BytesIO(content)) as stored:
        assert stored.format == "PNG"
        assert getattr(stored, "n_frames", 1) == 1


async def test_applies_exif_orientation_and_drops_metadata(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # rotar 90° para mostrar bien
    exif[0x010F] = "Fabricante"
    raw = _image("JPEG", (80, 40), exif=exif.tobytes())

    attachment = await _upload(sessionmaker_, raw)

    assert (attachment.width, attachment.height) == (40, 80)
    async with sessionmaker_() as session:
        content = await SqlAlchemyChatAttachmentRepository(session).get_content(attachment.id)
    assert content is not None
    with Image.open(io.BytesIO(content)) as stored:
        assert not stored.getexif()


async def test_a_transparent_png_keeps_its_alpha_channel(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    attachment = await _upload(sessionmaker_, _image("PNG", (20, 20), mode="RGBA"))

    async with sessionmaker_() as session:
        content = await SqlAlchemyChatAttachmentRepository(session).get_content(attachment.id)
    assert content is not None
    with Image.open(io.BytesIO(content)) as stored:
        assert stored.mode == "RGBA"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("factura.png", "factura.png"),
        ("../../etc/pass<wd>.png", "pass_wd_.png"),
        ("C:\\Users\\ana\\Mis fotos\\gato.jpg", "gato.jpg"),
        ("linea1\nlinea2.png", "linea1_linea2.png"),
        ("", "imagen"),
        (None, "imagen"),
        ("...", "imagen"),
    ],
)
def test_filenames_are_sanitized(raw: str | None, expected: str) -> None:
    assert sanitize_attachment_filename(raw) == expected


def test_filenames_are_capped_to_255_characters() -> None:
    assert len(sanitize_attachment_filename("a" * 400 + ".png")) <= 255


async def test_upload_discards_this_users_stale_unlinked_images_only(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    old_unlinked = await _upload(sessionmaker_, _image())
    old_other_user = await _upload(
        sessionmaker_, _image(), owner=ConversationOwner(user_id=8, erp_database_id=_OWNER_DB)
    )
    recent = await _upload(sessionmaker_, _image())
    stale_at = datetime.now(UTC) - timedelta(hours=25)
    async with sessionmaker_() as session:
        await session.execute(
            text("UPDATE chat_attachments SET created_at = :at WHERE id IN (:a, :b)"),
            {"at": _sqlite_time(stale_at), "a": old_unlinked.id.hex, "b": old_other_user.id.hex},
        )
        await session.commit()

    await _upload(sessionmaker_, _image())  # dispara la limpieza

    async with sessionmaker_() as session:
        repository = SqlAlchemyChatAttachmentRepository(session)
        assert await repository.get(old_unlinked.id) is None
        assert await repository.get_content(old_unlinked.id) is None
        assert await repository.get(old_other_user.id) is not None  # de otro usuario
        assert await repository.get(recent.id) is not None  # todavía vigente


async def test_upload_keeps_stale_images_that_were_sent_in_a_message(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    attachment = await _upload(sessionmaker_, _image())
    async with sessionmaker_() as session:
        repository = SqlAlchemyConversationRepository(session)
        conversation = await repository.save(
            Conversation(user_id=7, erp_database_id=_OWNER_DB, owner_erp_database_id=_OWNER_DB)
        )
        await repository.add_user_message_with_attachments(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content="mira"),
            link_attachment_ids=[attachment.id],
        )
        await session.execute(
            text("UPDATE chat_attachments SET created_at = :at"),
            {"at": _sqlite_time(datetime.now(UTC) - timedelta(days=3))},
        )
        await session.commit()

    await _upload(sessionmaker_, _image())

    async with sessionmaker_() as session:
        assert await SqlAlchemyChatAttachmentRepository(session).get(attachment.id) is not None


# ── Descarga ──────────────────────────────────────────────────────────────


async def test_the_owner_downloads_the_bytes(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    attachment = await _upload(sessionmaker_, _image("JPEG"))

    async with sessionmaker_() as session:
        found, content = await GetChatAttachmentUseCase(
            SqlAlchemyChatAttachmentRepository(session)
        ).execute(attachment.id, owner=_OWNER)

    assert found.mime == "image/jpeg"
    with Image.open(io.BytesIO(content)) as stored:
        assert stored.format == "JPEG"


@pytest.mark.parametrize(
    "stranger",
    [
        ConversationOwner(user_id=8, erp_database_id=_OWNER_DB),  # otro usuario
        ConversationOwner(user_id=7, erp_database_id=_OTHER_DB),  # mismo id, otro cliente
    ],
)
async def test_nobody_else_can_download_it(
    sessionmaker_: async_sessionmaker[AsyncSession], stranger: ConversationOwner
) -> None:
    attachment = await _upload(sessionmaker_, _image())

    async with sessionmaker_() as session:
        use_case = GetChatAttachmentUseCase(SqlAlchemyChatAttachmentRepository(session))
        with pytest.raises(ChatAttachmentNotFoundError):
            await use_case.execute(attachment.id, owner=stranger)
        with pytest.raises(ChatAttachmentNotFoundError):
            await use_case.execute(uuid4(), owner=_OWNER)


# ── Listado de mensajes ───────────────────────────────────────────────────


async def test_listing_messages_returns_attachment_metadata_without_loading_bytes(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> None:
    attachment = await _upload(sessionmaker_, _image("PNG", (90, 60)), filename="plano.png")
    async with sessionmaker_() as session:
        repository = SqlAlchemyConversationRepository(session)
        conversation = await repository.save(
            Conversation(user_id=7, erp_database_id=_OWNER_DB, owner_erp_database_id=_OWNER_DB)
        )
        saved = await repository.add_user_message_with_attachments(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content=""),
            link_attachment_ids=[attachment.id],
        )
        await session.commit()
        assert [a.id for a in saved.attachments] == [attachment.id]

    statements: list[str] = []
    async with sessionmaker_() as session:
        sync_engine = session.bind.sync_engine  # type: ignore[union-attr]

        def _record(conn, cursor, statement, *_args) -> None:  # noqa: ANN001
            statements.append(statement)

        event.listen(sync_engine, "before_cursor_execute", _record)
        try:
            messages = await SqlAlchemyConversationRepository(session).list_messages(
                conversation.id
            )
        finally:
            event.remove(sync_engine, "before_cursor_execute", _record)

    assert [m.attachments[0].filename for m in messages] == ["plano.png"]
    assert (messages[0].attachments[0].width, messages[0].attachments[0].height) == (90, 60)
    assert not any("chat_attachment_blobs" in sql for sql in statements)


async def test_message_response_exposes_attachments_and_defaults_to_empty() -> None:
    owner_db = uuid4()
    attachment = ChatAttachment(
        user_id=1,
        owner_erp_database_id=owner_db,
        mime="image/png",
        filename="a.png",
        size_bytes=10,
        width=3,
        height=2,
    )
    with_image = Message(role=MessageRole.USER, content="hola", attachments=[attachment])
    without = Message(role=MessageRole.USER, content="hola")

    response = MessageResponse.from_dto(ConversationMapper.message_to_dto(with_image))
    plain = MessageResponse.from_dto(ConversationMapper.message_to_dto(without))

    assert response.model_dump(mode="json")["attachments"] == [
        {
            "id": str(attachment.id),
            "mime": "image/png",
            "filename": "a.png",
            "size_bytes": 10,
            "width": 3,
            "height": 2,
        }
    ]
    assert plain.attachments == []


# ── HTTP ──────────────────────────────────────────────────────────────────


def _user(user_id: int = 7, database_id: UUID = _OWNER_DB) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id,
        login="USUARIO",
        full_name="Usuario",
        is_admin=False,
        is_active=True,
        erp_database_id=database_id,
    )


@pytest.fixture
def make_client(
    sessionmaker_: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., TestClient]]:
    current = {"user": _user()}

    def build(**env: str) -> TestClient:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        app = main_module.create_app()

        async def _session() -> AsyncIterator[AsyncSession]:
            async with sessionmaker_() as session:
                yield session
                await session.commit()

        app.dependency_overrides[get_agent_session] = _session
        app.dependency_overrides[get_current_user] = lambda: current["user"]
        client = TestClient(app)  # sin `with`: no corre el lifespan
        client.current = current  # type: ignore[attr-defined]
        return client

    yield build
    get_settings.cache_clear()


def _post(client: TestClient, content: bytes, filename: str = "foto.png"):
    return client.post("/chat/attachments", files={"file": (filename, content, "image/png")})


def test_http_upload_returns_201_with_metadata(make_client: Callable[..., TestClient]) -> None:
    client = make_client()

    response = _post(client, _image("PNG", (4000, 1000)), "ancha.png")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "mime", "filename", "size_bytes", "width", "height"}
    assert (body["mime"], body["filename"]) == ("image/png", "ancha.png")
    assert (body["width"], body["height"]) == (2048, 512)


def test_http_rejects_a_text_file_named_png_with_422(
    make_client: Callable[..., TestClient],
) -> None:
    response = _post(make_client(), b"no soy una imagen")

    assert response.status_code == 422
    assert "imagen" in response.json()["detail"]


def test_http_rejects_an_oversized_file_with_413(make_client: Callable[..., TestClient]) -> None:
    client = make_client(CHAT_IMAGE_MAX_MB="1")

    response = _post(client, b"0" * (2 * 1024 * 1024))

    assert response.status_code == 413
    body = response.json()
    assert body["errorCode"] == "file_too_large"
    assert body["limit_mb"] == 1
    assert "1 MB" in body["detail"]


def test_http_owner_downloads_bytes_with_content_type_and_private_cache(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    attachment_id = _post(client, _image("JPEG", (50, 50))).json()["id"]

    response = client.get(f"/chat/attachments/{attachment_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=86400"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (50, 50)


def test_http_another_user_gets_404(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    attachment_id = _post(client, _image()).json()["id"]

    client.current["user"] = _user(user_id=99)  # type: ignore[attr-defined]
    stranger = client.get(f"/chat/attachments/{attachment_id}")
    client.current["user"] = _user(database_id=_OTHER_DB)  # type: ignore[attr-defined]
    other_client = client.get(f"/chat/attachments/{attachment_id}")
    missing = client.get(f"/chat/attachments/{uuid4()}")

    assert stranger.status_code == other_client.status_code == missing.status_code == 404
    assert stranger.json() == missing.json()  # no se distingue "ajena" de "inexistente"


def test_http_upload_has_its_own_hourly_limit(make_client: Callable[..., TestClient]) -> None:
    client = make_client(RATE_LIMIT_CHAT_ATTACHMENTS_PER_HOUR="1")

    first = _post(client, _image())
    second = _post(client, _image())

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["errorCode"] == "rate_limited"
    assert "retry-after" in second.headers
