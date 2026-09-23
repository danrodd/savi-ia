"""La sesión del request confirma ANTES de mandar la respuesta.

Con el alcance por defecto de FastAPI el commit ocurría después: un cliente
que creaba una conversación y mandaba el primer mensaje en seguida recibía
404 porque la fila todavía no era visible.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from app.infrastructure.database import session as session_module
from app.infrastructure.database.session import AgentSessionDep


class _RecordingSession:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def commit(self) -> None:
        self._events.append("commit")

    async def rollback(self) -> None:
        self._events.append("rollback")


class _RecordingResponse(JSONResponse):
    events: list[str] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.events.append("response")
        await super().__call__(scope, receive, send)


def test_the_request_session_commits_before_the_response_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _RecordingResponse.events = events
    monkeypatch.setattr(
        session_module, "get_agent_sessionmaker", lambda: lambda: _RecordingSession(events)
    )
    app = FastAPI()

    @app.post("/create", response_class=_RecordingResponse)
    async def create(session: AgentSessionDep) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post("/create").status_code == 200

    assert events == ["commit", "response"]
