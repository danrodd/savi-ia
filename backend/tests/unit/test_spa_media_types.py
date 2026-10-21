"""El build del frontend se sirve con tipos fijos, sin depender del registro de Windows."""

import mimetypes
from collections.abc import Iterator
from pathlib import Path

import pytest
import starlette.responses
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    dist = tmp_path / "frontend"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SAVI</title>", encoding="utf-8")
    (dist / "theme-init.js").write_text(";(() => {})()", encoding="utf-8")
    (dist / "assets" / "index-abc.js").write_text("export {}", encoding="utf-8")
    (dist / "assets" / "index-abc.css").write_text("body{}", encoding="utf-8")
    monkeypatch.setattr(main_module, "resource_dir", lambda: tmp_path)
    app = FastAPI()
    main_module._mount_frontend(app)  # pyright: ignore[reportPrivateUsage]
    yield TestClient(app)


@pytest.fixture
def broken_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula un Windows donde otro programa registró `.js` y `.css` como texto plano."""
    real_guess = mimetypes.guess_type

    def guess(url: object, strict: bool = True) -> tuple[str | None, str | None]:
        if str(url).endswith((".js", ".css")):
            return "text/plain", None
        return real_guess(str(url), strict)

    # Starlette importa `guess_type` en su módulo: se parchea ahí.
    monkeypatch.setattr(starlette.responses, "guess_type", guess)


@pytest.mark.usefixtures("broken_registry")
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/theme-init.js", "text/javascript"),
        ("/assets/index-abc.js", "text/javascript"),
        ("/assets/index-abc.css", "text/css"),
        ("/", "text/html"),
        ("/perfil", "text/html"),
    ],
)
def test_spa_files_keep_their_type_even_with_a_broken_registry(
    client: TestClient, path: str, expected: str
) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(expected)
