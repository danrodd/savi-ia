"""Feedback 👍/👎 por respuesta: endpoints del usuario y panel del administrador.

SQLite real (mismo metadata que producción), app real y sin lifespan: lo que
importa es qué queda guardado, quién lo puede tocar y qué se expone.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main as main_module
from app.infrastructure.config import get_settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_agent_session
from app.modules.auth.domain.entities import AuthenticatedUser
from app.modules.auth.infrastructure.http.dependencies import get_current_user
from app.modules.company_knowledge.infrastructure.http.repository_dependency import (
    get_document_repository,
)
from app.modules.conversations.infrastructure.persistence.models import (
    ConversationModel,
    MessageModel,
)
from app.modules.erp_databases.infrastructure.http.dependencies import (
    get_resolve_modules_for_database_use_case,
)
from app.modules.erp_databases.infrastructure.persistence.models import ErpDatabaseModel
from app.modules.feedback.infrastructure.persistence.models import MessageFeedbackModel

_DB_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DB_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_SECRET_SQL = "SELECT secreto FROM tabla_privada WHERE clave = 'XYZ'"


def _erp(database_id: UUID, code: str) -> ErpDatabaseModel:
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


def _user(
    user_id: int = 7,
    database_id: UUID = _DB_A,
    *,
    admin: bool = False,
    login: str = "AGENTE",
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id,
        login=login,
        full_name=f"Nombre {login}",
        is_admin=admin,
        is_active=True,
        erp_database_id=database_id,
    )


@pytest_asyncio.fixture
async def sm(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'fb.db').as_posix()}")

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
        s.add(_erp(_DB_A, "NORTE"))
        s.add(_erp(_DB_B, "SUR"))
        await s.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def make_client(
    sm: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[AuthenticatedUser], TestClient]]:
    clients: list[TestClient] = []

    def build(user: AuthenticatedUser) -> TestClient:
        monkeypatch.setenv("SAVI_ADMIN_LOGINS", "")
        get_settings.cache_clear()
        app = main_module.create_app()

        async def _session() -> AsyncIterator[AsyncSession]:
            async with sm() as session:
                yield session
                await session.commit()

        app.dependency_overrides[get_agent_session] = _session
        app.dependency_overrides[get_current_user] = lambda: user
        # Sin fuentes citadas el repositorio de documentos no se usa.
        app.dependency_overrides[get_document_repository] = lambda: None
        app.dependency_overrides[get_resolve_modules_for_database_use_case] = lambda: None
        client = TestClient(app)  # sin `with`: no corre el lifespan
        clients.append(client)
        return client

    yield build
    get_settings.cache_clear()


class Seeded:
    def __init__(self, conversation_id: UUID, question_id: UUID, answer_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.question_id = question_id
        self.answer_id = answer_id

    def url(self, message_id: UUID | None = None) -> str:
        return (
            f"/conversations/{self.conversation_id}/messages/"
            f"{message_id or self.answer_id}/feedback"
        )


async def _seed(
    sm: async_sessionmaker[AsyncSession],
    *,
    user_id: int = 7,
    owner_db: UUID = _DB_A,
    queried_db: UUID = _DB_A,
    question: str = "¿Cuánto vendimos ayer?",
    answer: str = "Vendiste 10 millones.",
    provider: str = "claude",
    model: str = "claude-sonnet",
    created: datetime | None = None,
) -> Seeded:
    base = created or datetime.now(UTC) - timedelta(minutes=5)
    conversation_id, question_id, answer_id = uuid4(), uuid4(), uuid4()
    async with sm() as s:
        s.add(
            ConversationModel(
                id=conversation_id,
                user_id=user_id,
                erp_database_id=queried_db,
                owner_erp_database_id=owner_db,
                title="Hilo",
            )
        )
        await s.flush()
        s.add(
            MessageModel(
                id=question_id,
                conversation_id=conversation_id,
                role="user",
                content=question,
                created_at=base,
            )
        )
        s.add(
            MessageModel(
                id=answer_id,
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                provider=provider,
                model=model,
                cost_usd=0.012345,
                tool_invocations=[
                    {
                        "id": "t1",
                        "name": "consultar_datos",
                        "input": {"sql": _SECRET_SQL},
                        "status": "ok",
                    }
                ],
                created_at=base + timedelta(seconds=3),
            )
        )
        await s.commit()
    return Seeded(conversation_id, question_id, answer_id)


async def _count_rows(sm: async_sessionmaker[AsyncSession]) -> int:
    async with sm() as s:
        return int((await s.execute(select(func.count(MessageFeedbackModel.id)))).scalar_one())


# ── Usuario: PUT / DELETE ─────────────────────────────────────────────────


async def test_put_creates_and_replaces_a_single_row(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm)
    client = make_client(_user())

    first = client.put(seeded.url(), json={"rating": "up"})
    assert first.status_code == 200
    assert first.json()["rating"] == "up"
    assert first.json()["reason"] is None

    second = client.put(
        seeded.url(),
        json={"rating": "down", "reason": "dato_incorrecto", "comment": "  Faltó el IVA  "},
    )
    assert second.status_code == 200
    body = second.json()
    assert (body["rating"], body["reason"], body["comment"]) == (
        "down",
        "dato_incorrecto",
        "Faltó el IVA",
    )
    assert body["message_id"] == str(seeded.answer_id)
    assert await _count_rows(sm) == 1


async def test_switching_back_to_up_drops_the_reason(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm)
    client = make_client(_user())
    client.put(seeded.url(), json={"rating": "down", "reason": "incompleta"})

    response = client.put(seeded.url(), json={"rating": "up"})

    assert response.status_code == 200
    assert response.json()["reason"] is None


async def test_get_conversation_exposes_feedback_and_null_when_absent(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm)
    client = make_client(_user())

    before = client.get(f"/conversations/{seeded.conversation_id}").json()["messages"]
    assert [m["feedback"] for m in before] == [None, None]

    client.put(seeded.url(), json={"rating": "down", "reason": "muy_lenta", "comment": "Lenta"})
    after = {
        m["id"]: m
        for m in client.get(f"/conversations/{seeded.conversation_id}").json()["messages"]
    }
    assert after[str(seeded.answer_id)]["feedback"] == {
        "rating": "down",
        "reason": "muy_lenta",
        "comment": "Lenta",
    }
    assert after[str(seeded.question_id)]["feedback"] is None


async def test_delete_is_idempotent_and_removes_the_rating(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm)
    client = make_client(_user())
    client.put(seeded.url(), json={"rating": "up"})

    assert client.delete(seeded.url()).status_code == 204
    assert client.delete(seeded.url()).status_code == 204
    assert await _count_rows(sm) == 0
    messages = client.get(f"/conversations/{seeded.conversation_id}").json()["messages"]
    assert all(m["feedback"] is None for m in messages)


async def test_other_user_gets_404_and_cannot_touch_the_rating(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm, user_id=7)
    owner = make_client(_user(7))
    owner.put(seeded.url(), json={"rating": "up"})

    stranger = make_client(_user(8))
    assert stranger.put(seeded.url(), json={"rating": "down"}).status_code == 404
    assert stranger.delete(seeded.url()).status_code == 404
    assert await _count_rows(sm) == 1


async def test_same_user_id_in_another_database_is_a_different_person(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    """El `idUsuario` se repite entre clientes: sin la base no es la misma persona."""
    seeded = await _seed(sm, user_id=7, owner_db=_DB_A)
    namesake = make_client(_user(7, _DB_B))

    assert namesake.put(seeded.url(), json={"rating": "up"}).status_code == 404
    assert await _count_rows(sm) == 0


async def test_ratings_are_scoped_by_user_and_database_on_read(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm, user_id=7, owner_db=_DB_A)
    make_client(_user(7, _DB_A)).put(seeded.url(), json={"rating": "up"})
    # Fila de OTRA persona sobre el mismo mensaje (no debería poder existir por
    # la API; se inserta directo para fijar que la lectura la ignora).
    async with sm() as s:
        s.add(
            MessageFeedbackModel(
                message_id=seeded.answer_id,
                user_id=99,
                owner_erp_database_id=_DB_B,
                rating="down",
                reason="otra",
            )
        )
        await s.commit()

    messages = (
        make_client(_user(7, _DB_A))
        .get(f"/conversations/{seeded.conversation_id}")
        .json()["messages"]
    )
    answer = next(m for m in messages if m["id"] == str(seeded.answer_id))
    assert answer["feedback"]["rating"] == "up"


async def test_superseded_and_user_messages_are_rejected(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm)
    async with sm() as s:
        message = await s.get(MessageModel, seeded.answer_id)
        assert message is not None
        message.superseded_at = datetime.now(UTC)
        await s.commit()
    client = make_client(_user())

    assert client.put(seeded.url(), json={"rating": "up"}).status_code == 422
    assert client.put(seeded.url(seeded.question_id), json={"rating": "up"}).status_code == 422
    assert await _count_rows(sm) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"rating": "up", "reason": "incompleta"},
        {"rating": "down", "reason": "inventado"},
        {"rating": "meh"},
        {"rating": "down", "comment": "x" * 1001},
    ],
)
async def test_invalid_payloads_are_422(
    sm: async_sessionmaker[AsyncSession],
    make_client: Callable[..., TestClient],
    payload: dict[str, Any],
) -> None:
    seeded = await _seed(sm)

    response = make_client(_user()).put(seeded.url(), json=payload)

    assert response.status_code == 422
    assert await _count_rows(sm) == 0


async def test_deleted_conversation_and_unknown_message_are_404(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm)
    client = make_client(_user())

    assert client.put(seeded.url(uuid4()), json={"rating": "up"}).status_code == 404
    assert client.delete(f"/conversations/{uuid4()}/messages/{uuid4()}/feedback").status_code == 404
    client.delete(f"/conversations/{seeded.conversation_id}")
    assert client.put(seeded.url(), json={"rating": "up"}).status_code == 404


async def test_put_is_rate_limited(
    sm: async_sessionmaker[AsyncSession],
    make_client: Callable[..., TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_FEEDBACK_PER_MINUTE", "2")
    seeded = await _seed(sm)
    client = make_client(_user())

    codes = [client.put(seeded.url(), json={"rating": "up"}).status_code for _ in range(3)]

    assert codes == [200, 200, 429]


# ── Administrador ─────────────────────────────────────────────────────────


async def _rate(
    make_client: Callable[..., TestClient], seeded: Seeded, user: AuthenticatedUser, **body: Any
) -> None:
    response = make_client(user).put(seeded.url(), json=body)
    assert response.status_code == 200, response.text


async def test_admin_endpoints_require_a_company_admin(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    client = make_client(_user(7, _DB_A, admin=False))

    for path in ("/admin/feedback", "/admin/feedback/summary", "/admin/feedback/export.csv"):
        assert client.get(path).status_code == 403, path


async def test_admin_list_has_context_and_never_leaks_tool_inputs(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm, queried_db=_DB_B, answer="A" * 5000, question="Q" * 3000)
    await _rate(
        make_client,
        seeded,
        _user(7, _DB_A),
        rating="down",
        reason="no_entendio",
        comment="No respondió lo que pedí",
    )

    response = make_client(_user(1, _DB_A, admin=True, login="ADMIN")).get("/admin/feedback")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["rating"] == "down"
    assert item["reason"] == "no_entendio"
    assert item["comment"] == "No respondió lo que pedí"
    assert item["user_login"] == "AGENTE"
    assert item["user_name"] == "Nombre AGENTE"
    assert item["conversation_id"] == str(seeded.conversation_id)
    assert item["message_id"] == str(seeded.answer_id)
    assert len(item["question"]) == 2000
    assert len(item["answer"]) == 4000
    assert item["provider"] == "claude"
    assert item["model"] == "claude-sonnet"
    assert item["cost_usd"] == pytest.approx(0.012345)
    assert item["tools"] == ["consultar_datos"]
    # Base CONSULTADA (cliente atendido), no la de identidad del agente.
    assert item["database_code"] == "SUR"
    assert _SECRET_SQL not in response.text
    assert "secreto" not in response.text


async def test_question_is_the_user_message_right_before_the_answer(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(sm, question="Primera pregunta")
    async with sm() as s:
        later = datetime.now(UTC)
        second_user = uuid4()
        second_answer = uuid4()
        s.add(
            MessageModel(
                id=second_user,
                conversation_id=seeded.conversation_id,
                role="user",
                content="Segunda pregunta",
                created_at=later,
            )
        )
        s.add(
            MessageModel(
                id=second_answer,
                conversation_id=seeded.conversation_id,
                role="assistant",
                content="Segunda respuesta",
                created_at=later + timedelta(seconds=2),
            )
        )
        await s.commit()
    client = make_client(_user(7, _DB_A))
    client.put(seeded.url(second_answer), json={"rating": "up"})
    client.put(seeded.url(), json={"rating": "up"})

    items = make_client(_user(1, _DB_A, admin=True)).get("/admin/feedback").json()["items"]

    by_answer = {i["answer"]: i["question"] for i in items}
    assert by_answer == {
        "Vendiste 10 millones.": "Primera pregunta",
        "Segunda respuesta": "Segunda pregunta",
    }


async def test_admin_is_scoped_to_their_own_database(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    mine = await _seed(sm, user_id=7, owner_db=_DB_A)
    theirs = await _seed(sm, user_id=7, owner_db=_DB_B, question="Pregunta del otro cliente")
    await _rate(make_client, mine, _user(7, _DB_A), rating="up")
    await _rate(make_client, theirs, _user(7, _DB_B), rating="down", reason="otra")

    admin_a = make_client(_user(1, _DB_A, admin=True))
    admin_b = make_client(_user(1, _DB_B, admin=True))

    a_items = admin_a.get("/admin/feedback").json()["items"]
    b_items = admin_b.get("/admin/feedback").json()["items"]
    assert [i["message_id"] for i in a_items] == [str(mine.answer_id)]
    assert [i["message_id"] for i in b_items] == [str(theirs.answer_id)]
    assert admin_a.get("/admin/feedback/summary").json()["total"] == 1
    assert "Pregunta del otro cliente" not in admin_a.get("/admin/feedback/export.csv").text


async def test_admin_filters(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    day = datetime(2026, 5, 4, 15, 0, tzinfo=UTC)
    up = await _seed(sm, user_id=1, provider="claude", model="m1", created=day)
    down = await _seed(sm, user_id=2, provider="gemini", model="m2", created=day)
    other = await _seed(sm, user_id=3, provider="claude", model="m1", created=day)
    await _rate(make_client, up, _user(1, login="ANA"), rating="up")
    await _rate(
        make_client,
        down,
        _user(2, login="BETO"),
        rating="down",
        reason="incompleta",
        comment="Faltan 100% de los totales_",
    )
    await _rate(make_client, other, _user(3, login="CARLA"), rating="down", reason="muy_lenta")
    admin = make_client(_user(9, _DB_A, admin=True, login="ADMIN"))

    def ids(**params: str) -> set[str]:
        response = admin.get("/admin/feedback", params=params)
        assert response.status_code == 200, response.text
        return {i["user_login"] for i in response.json()["items"]}

    assert ids() == {"ANA", "BETO", "CARLA"}
    assert ids(rating="up") == {"ANA"}
    assert ids(rating="down") == {"BETO", "CARLA"}
    assert ids(reason="incompleta") == {"BETO"}
    assert ids(provider="gemini") == {"BETO"}
    assert ids(model="m1") == {"ANA", "CARLA"}
    assert ids(user="et") == {"BETO"}
    assert ids(q="totales") == {"BETO"}
    # Comodines de LIKE tratados como texto literal.
    assert ids(q="100%") == {"BETO"}
    assert ids(q="%") == {"BETO"}
    assert ids(q="zzz") == set()
    assert ids(**{"from": "2026-05-04", "to": "2026-05-04"}) == set()  # creadas "hoy", no el 4
    assert ids(**{"from": "2000-01-01", "to": "2999-01-01"}) == {"ANA", "BETO", "CARLA"}
    assert (
        admin.get("/admin/feedback", params={"from": "2026-05-05", "to": "2026-05-01"}).status_code
        == 422
    )


async def test_admin_pagination(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    for i in range(3):
        seeded = await _seed(sm, user_id=100 + i)
        await _rate(make_client, seeded, _user(100 + i, login=f"U{i}"), rating="up")
    admin = make_client(_user(9, _DB_A, admin=True))

    page = admin.get("/admin/feedback", params={"limit": 2, "offset": 0}).json()
    rest = admin.get("/admin/feedback", params={"limit": 2, "offset": 2}).json()

    assert (page["total"], len(page["items"])) == (3, 2)
    assert (rest["total"], len(rest["items"])) == (3, 1)


async def test_admin_summary(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    specs = [
        (1, "up", None, "claude", "m1"),
        (2, "up", None, "claude", "m1"),
        (3, "down", "dato_incorrecto", "claude", "m1"),
        (4, "down", "dato_incorrecto", "gemini", "m2"),
        (5, "down", "muy_lenta", "gemini", "m2"),
    ]
    for uid, rating, reason, provider, model in specs:
        seeded = await _seed(sm, user_id=uid, provider=provider, model=model)
        body: dict[str, Any] = {"rating": rating}
        if reason:
            body["reason"] = reason
        await _rate(make_client, seeded, _user(uid, login=f"U{uid}"), **body)

    summary = make_client(_user(9, _DB_A, admin=True)).get("/admin/feedback/summary").json()

    assert (summary["total"], summary["up"], summary["down"]) == (5, 2, 3)
    assert summary["positive_pct"] == 40.0
    assert summary["top_reasons"][0] == {"reason": "dato_incorrecto", "count": 2}
    assert {r["reason"] for r in summary["top_reasons"]} == {"dato_incorrecto", "muy_lenta"}
    assert sum(d["up"] + d["down"] for d in summary["daily"]) == 5
    models = {(m["provider"], m["model"]): (m["up"], m["down"]) for m in summary["by_model"]}
    assert models == {("claude", "m1"): (2, 1), ("gemini", "m2"): (0, 2)}


async def test_admin_summary_without_data_has_no_percentage(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    summary = make_client(_user(9, _DB_A, admin=True)).get("/admin/feedback/summary").json()

    assert summary["total"] == 0
    assert summary["positive_pct"] is None
    assert summary["daily"] == []


async def test_export_csv_has_bom_semicolons_and_no_tool_inputs(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    seeded = await _seed(
        sm, question='=HYPERLINK("http://x")', answer="Vendiste; 10 millones.\nGracias"
    )
    await _rate(
        make_client,
        seeded,
        _user(7),
        rating="down",
        reason="dato_incorrecto",
        comment='Está "mal"; revisen',
    )

    response = make_client(_user(9, _DB_A, admin=True)).get("/admin/feedback/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    raw = response.content
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header.startswith("Fecha;Usuario;Nombre;Calificación;Motivo;Comentario;Pregunta;")
    assert header.count(";") == 14
    # Fórmulas neutralizadas y el `;` dentro de un valor queda entre comillas.
    assert "'=HYPERLINK" in text
    assert '"Vendiste; 10 millones.\nGracias"' in text
    assert "El dato es incorrecto" in text
    assert "consultar_datos" in text
    assert _SECRET_SQL not in text


async def test_export_respects_filters(
    sm: async_sessionmaker[AsyncSession], make_client: Callable[..., TestClient]
) -> None:
    up = await _seed(sm, user_id=1, question="Pregunta positiva")
    down = await _seed(sm, user_id=2, question="Pregunta negativa")
    await _rate(make_client, up, _user(1), rating="up")
    await _rate(make_client, down, _user(2), rating="down")

    text = (
        make_client(_user(9, _DB_A, admin=True))
        .get("/admin/feedback/export.csv", params={"rating": "down"})
        .content.decode("utf-8-sig")
    )

    assert "Pregunta negativa" in text
    assert "Pregunta positiva" not in text
