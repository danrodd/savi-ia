"""Primitivas del TOTP (RFC 6238) y su repositorio.

El resto del flujo (desafío, configuración, verificación, HTTP) está en `test_mfa_flow.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.infrastructure.database.base import Base
from app.modules.auth.infrastructure.persistence import SqlAlchemyTotpRepository
from app.shared.security import CredentialCipher, CredentialDecryptError, totp

# Secreto ASCII "12345678901234567890" en base32 (el vector del RFC 6238, Apéndice B).
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


# ── primitivas ────────────────────────────────────────────────────────────────────────────
def test_rfc6238_vector() -> None:
    # T=59 s -> paso 1 -> 94287082 con 8 dígitos; con 6 dígitos, 287082.
    assert totp.code_at(RFC_SECRET, 59 // 30) == "287082"


def test_accepts_the_window_and_rejects_outside_it() -> None:
    now = _at(1_700_000_010)
    step = totp.current_step(now)
    for offset in (-1, 0, 1):
        assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step + offset), now, 0) == (
            step + offset
        )
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step + 2), now, 0) is None
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 2), now, 0) is None


def test_a_used_code_is_not_accepted_twice() -> None:
    now = _at(1_700_000_010)
    step = totp.current_step(now)
    code = totp.code_at(RFC_SECRET, step)

    assert totp.verify(RFC_SECRET, code, now, last_step=step - 1) == step
    assert totp.verify(RFC_SECRET, code, now, last_step=step) is None
    # Tampoco un código de un paso anterior al último aceptado.
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 1), now, last_step=step) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "12ab56", "      "])
def test_rejects_malformed_codes(code: str) -> None:
    assert totp.verify(RFC_SECRET, code, _at(1_700_000_010), 0) is None


def test_tolerates_spaces_in_the_code() -> None:
    now = _at(1_700_000_010)
    code = totp.code_at(RFC_SECRET, totp.current_step(now))
    assert totp.verify(RFC_SECRET, f"{code[:3]} {code[3:]}", now, 0) is not None


def test_generated_secret_is_valid_base32_of_160_bits() -> None:
    secret = totp.generate_secret()
    assert len(secret) == 32
    assert totp.code_at(secret, 1)  # no levanta
    assert totp.generate_secret() != secret


def test_otpauth_uri() -> None:
    uri = totp.otpauth_uri("ABC234", "JPEREZ@NORTE", "SAVI Master")
    assert uri.startswith("otpauth://totp/SAVI%20Master%3AJPEREZ%40NORTE?")
    assert "secret=ABC234" in uri
    assert "issuer=SAVI%20Master" in uri
    assert "period=30" in uri and "digits=6" in uri


# ── repositorio (SQLite real) ─────────────────────────────────────────────────────────────
class _ReversibleCipher(CredentialCipher):
    """Cifrado de juguete reversible, para verificar que el secreto no se guarda en claro."""

    def __init__(self) -> None:
        self.broken = False

    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext[::-1]}"

    def decrypt(self, ciphertext: str) -> str:
        if self.broken:
            raise CredentialDecryptError("clave cambiada")
        return ciphertext.removeprefix("enc:")[::-1]


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'totp.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def cipher() -> _ReversibleCipher:
    return _ReversibleCipher()


@pytest.fixture
def repo(engine: AsyncEngine, cipher: _ReversibleCipher) -> SqlAlchemyTotpRepository:
    return SqlAlchemyTotpRepository(async_sessionmaker(engine, expire_on_commit=False), cipher)


NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


async def test_pending_then_enabled(repo: SqlAlchemyTotpRepository) -> None:
    db = uuid4()
    await repo.save_pending(
        erp_database_id=db, user_id=7, user_login="JPEREZ", secret="SECRETO", when=NOW
    )

    pending = await repo.get(erp_database_id=db, user_id=7)
    assert pending is not None
    assert pending.secret == "SECRETO"
    assert not pending.enabled

    assert await repo.enable(erp_database_id=db, user_id=7, last_step=99, when=NOW)
    enabled = await repo.get(erp_database_id=db, user_id=7)
    assert enabled is not None and enabled.enabled and enabled.last_step == 99
    # Activar de nuevo no hace nada: ya no está pendiente.
    assert not await repo.enable(erp_database_id=db, user_id=7, last_step=100, when=NOW)


async def test_secret_is_stored_encrypted(
    repo: SqlAlchemyTotpRepository, engine: AsyncEngine
) -> None:
    from sqlalchemy import text

    await repo.save_pending(
        erp_database_id=uuid4(), user_id=1, user_login="A", secret="SECRETO", when=NOW
    )
    async with engine.connect() as conn:
        raw = (await conn.execute(text("SELECT secret_encrypted FROM user_totp"))).scalar_one()
    assert raw != "SECRETO"
    assert "SECRETO" not in raw


async def test_pending_is_replaced_but_enabled_is_never_overwritten(
    repo: SqlAlchemyTotpRepository,
) -> None:
    db = uuid4()
    await repo.save_pending(erp_database_id=db, user_id=1, user_login="A", secret="UNO", when=NOW)
    await repo.save_pending(erp_database_id=db, user_id=1, user_login="A", secret="DOS", when=NOW)
    record = await repo.get(erp_database_id=db, user_id=1)
    assert record is not None and record.secret == "DOS"

    await repo.enable(erp_database_id=db, user_id=1, last_step=5, when=NOW)
    with pytest.raises(ValueError):
        await repo.save_pending(
            erp_database_id=db, user_id=1, user_login="A", secret="TRES", when=NOW
        )


async def test_advance_step_is_conditional(repo: SqlAlchemyTotpRepository) -> None:
    """Dos pedidos con el mismo código compiten por la fila: solo uno la avanza."""
    db = uuid4()
    await repo.save_pending(erp_database_id=db, user_id=1, user_login="A", secret="S", when=NOW)
    await repo.enable(erp_database_id=db, user_id=1, last_step=10, when=NOW)

    assert await repo.advance_step(erp_database_id=db, user_id=1, step=11)
    assert not await repo.advance_step(erp_database_id=db, user_id=1, step=11)
    assert not await repo.advance_step(erp_database_id=db, user_id=1, step=5)
    assert await repo.advance_step(erp_database_id=db, user_id=1, step=12)


async def test_identity_is_database_plus_user(repo: SqlAlchemyTotpRepository) -> None:
    """El `idUsuario` se repite entre clientes: dos bases, dos segundos factores."""
    a, b = uuid4(), uuid4()
    await repo.save_pending(erp_database_id=a, user_id=5, user_login="X", secret="A", when=NOW)
    await repo.save_pending(erp_database_id=b, user_id=5, user_login="X", secret="B", when=NOW)

    first = await repo.get(erp_database_id=a, user_id=5)
    second = await repo.get(erp_database_id=b, user_id=5)
    assert first is not None and first.secret == "A"
    assert second is not None and second.secret == "B"


async def test_delete_by_login_scopes_to_the_database(repo: SqlAlchemyTotpRepository) -> None:
    a, b = uuid4(), uuid4()
    await repo.save_pending(erp_database_id=a, user_id=5, user_login="X", secret="A", when=NOW)
    await repo.save_pending(erp_database_id=b, user_id=5, user_login="X", secret="B", when=NOW)

    assert await repo.delete_by_login(erp_database_id=a, user_login="X") == 5
    assert await repo.get(erp_database_id=a, user_id=5) is None
    assert await repo.get(erp_database_id=b, user_id=5) is not None
    assert await repo.delete_by_login(erp_database_id=a, user_login="X") is None


async def test_unreadable_secret_is_reported_not_raised(
    repo: SqlAlchemyTotpRepository, cipher: _ReversibleCipher
) -> None:
    """Cambió la clave del servidor: el usuario queda marcado, no se tumba el login."""
    db = uuid4()
    await repo.save_pending(erp_database_id=db, user_id=1, user_login="A", secret="S", when=NOW)
    cipher.broken = True

    record = await repo.get(erp_database_id=db, user_id=1)

    assert record is not None
    assert record.unreadable
    assert record.secret is None
