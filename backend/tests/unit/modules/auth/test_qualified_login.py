"""Tests del login calificado (`JPEREZ@NORTE`) y del subject del JWT.

Lo que se protege:

- El identificador de cliente resuelve UNA base, siempre. Nunca hay
  cascada sobre las demás.
- Un cliente inexistente responde exactamente igual que una contraseña
  mala, y en el mismo tiempo: si no, se pueden enumerar los clientes.
- El JWT lleva la identidad calificada, y un token viejo (sin base) se
  rechaza en vez de atribuirse a la default.
"""
from __future__ import annotations

import time
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.infrastructure.config.settings import Settings
from app.modules.auth.application.use_cases.login import (
    LoginUseCase,
    split_qualified_login,
)
from app.modules.auth.domain.entities import AuthenticatedUser, RefreshTokenRecord
from app.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.modules.auth.domain.interfaces import (
    PasswordHasher,
    RefreshTokenRepository,
    UserRepository,
    UserRepositoryFactory,
)
from app.modules.auth.domain.interfaces.user_repository import UserWithHash
from app.modules.auth.domain.value_objects import TokenPurpose
from app.modules.auth.infrastructure.security import JwtTokenService

_DATABASE_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_DATABASE_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_PASSWORD_HASH = "hash-correcto"


# ── Partición del login ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("JPEREZ", ("JPEREZ", None)),
        ("JPEREZ@NORTE", ("JPEREZ", "NORTE")),
        ("  JPEREZ@NORTE  ", ("JPEREZ", "NORTE")),
        # `rsplit`: si el codigo del ERP tuviera un `@`, gana el último.
        ("raro@cosa@NORTE", ("raro@cosa", "NORTE")),
        # Formas degeneradas: se tratan como login sin calificar para que
        # fallen como credencial inválida y no como error de formato.
        ("@NORTE", ("@NORTE", None)),
        ("JPEREZ@", ("JPEREZ@", None)),
    ],
)
def test_split_qualified_login(raw: str, expected: tuple[str, str | None]) -> None:
    assert split_qualified_login(raw) == expected


# ── Dobles ───────────────────────────────────────────────────────────


class _FakeUserRepo(UserRepository):
    def __init__(self, database_id: UUID, logins: set[str]) -> None:
        self.database_id = database_id
        self._logins = logins

    async def find_by_login(self, login: str) -> UserWithHash | None:
        if login not in self._logins:
            return None
        return UserWithHash(
            user=AuthenticatedUser(
                id=5,  # el mismo idUsuario en las dos bases, a propósito
                erp_database_id=self.database_id,
                login=login,
                full_name="Juan Pérez",
                is_admin=False,
                is_active=True,
            ),
            password_hash=_PASSWORD_HASH,
        )


class _FakeFactory(UserRepositoryFactory):
    """Dos clientes registrados: NORTE (default) y SUR."""

    def __init__(self) -> None:
        self.resolved_codes: list[str | None] = []
        self._by_code = {
            "NORTE": _FakeUserRepo(_DATABASE_A, {"JPEREZ"}),
            "SUR": _FakeUserRepo(_DATABASE_B, {"MGOMEZ"}),
        }

    async def for_code(self, code: str | None) -> UserRepository | None:
        self.resolved_codes.append(code)
        return self._by_code.get(code or "NORTE")

    async def for_database_id(self, database_id: UUID) -> UserRepository | None:
        for repo in self._by_code.values():
            if repo.database_id == database_id:
                return repo
        return None


class _FakeHasher(PasswordHasher):
    def verify(self, plain: str, hashed: str) -> bool:  # noqa: ARG002
        return plain == "correcta" and hashed == _PASSWORD_HASH

    def hash(self, plain: str) -> str:
        return _PASSWORD_HASH


class _FakeRefreshRepo(RefreshTokenRepository):
    def __init__(self) -> None:
        self.saved: list[RefreshTokenRecord] = []

    async def save(self, record: RefreshTokenRecord) -> None:
        self.saved.append(record)

    async def get_by_jti(self, jti: UUID) -> RefreshTokenRecord | None:
        return next((r for r in self.saved if r.jti == jti), None)

    async def revoke(self, jti: UUID, *, when: datetime) -> bool:  # noqa: ARG002
        return True

    async def revoke_all_for_user(
        self, user_id: int, *, erp_database_id: UUID, when: datetime
    ) -> None: ...


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        agent_db_engine="sqlite",
        jwt_secret="secreto-de-test-suficientemente-largo-para-hs256",
        erp_credentials_key="sIYQBhcJUxE6vsRRrJvVKa3CtoUj_o8SPDBSAcHDCyM=",
    )


def _use_case() -> tuple[LoginUseCase, _FakeFactory, _FakeRefreshRepo]:
    factory = _FakeFactory()
    refresh = _FakeRefreshRepo()
    return (
        LoginUseCase(factory, refresh, _FakeHasher(), JwtTokenService(_settings())),
        factory,
        refresh,
    )


# ── Resolución de la base ────────────────────────────────────────────


async def test_qualified_login_resolves_that_client_only() -> None:
    use_case, factory, _ = _use_case()

    _, user = await use_case.execute("MGOMEZ@SUR", "correcta")

    assert user.erp_database_id == _DATABASE_B
    # Una sola resolución: nunca se recorren las demás bases.
    assert factory.resolved_codes == ["SUR"]


async def test_login_without_separator_uses_the_default() -> None:
    use_case, factory, _ = _use_case()

    _, user = await use_case.execute("JPEREZ", "correcta")

    assert user.erp_database_id == _DATABASE_A
    assert factory.resolved_codes == [None]


async def test_user_of_another_client_is_not_found_in_this_one() -> None:
    """No hay cascada: `MGOMEZ` existe en SUR, pero pedirlo en NORTE
    falla en vez de buscarlo en la otra base."""
    use_case, factory, _ = _use_case()

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute("MGOMEZ@NORTE", "correcta")

    assert factory.resolved_codes == ["NORTE"]


async def test_refresh_record_carries_the_database() -> None:
    use_case, _, refresh = _use_case()

    await use_case.execute("MGOMEZ@SUR", "correcta")

    assert refresh.saved[0].erp_database_id == _DATABASE_B
    assert refresh.saved[0].user_id == 5


# ── Sin enumeración de clientes ──────────────────────────────────────


@pytest.mark.parametrize(
    "intento",
    [
        "JPEREZ@NOEXISTE",  # cliente inexistente
        "NOEXISTE@NORTE",  # usuario inexistente
        "JPEREZ@NORTE",  # usuario correcto, contraseña mala
    ],
)
async def test_every_failure_gives_the_same_error(intento: str) -> None:
    use_case, _, _ = _use_case()

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(intento, "incorrecta")


async def test_failed_logins_take_the_same_minimum_time() -> None:
    """El piso de duración cierra el oráculo de tiempo.

    Sin él, "el cliente no existe" corta antes de ir a la BD del ERP y
    responde mucho más rápido que "la contraseña está mal" — medido
    contra el ERP real, 3,4 ms contra 14 ms. Esa diferencia permite
    enumerar los clientes registrados cronometrando respuestas.
    """
    use_case, _, _ = _use_case()
    elapsed: list[float] = []

    for intento in ("JPEREZ@NOEXISTE", "JPEREZ@NORTE"):
        started = time.perf_counter()
        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(intento, "incorrecta")
        elapsed.append(time.perf_counter() - started)

    # Los dos caminos llegan al piso; la diferencia entre ellos es ruido
    # del timer, no información sobre si el cliente existe.
    assert all(e >= 0.2 for e in elapsed)
    assert abs(elapsed[0] - elapsed[1]) < 0.05


# ── Subject calificado del JWT ───────────────────────────────────────


async def test_access_token_carries_the_qualified_identity() -> None:
    use_case, _, _ = _use_case()
    tokens = JwtTokenService(_settings())

    pair, _ = await use_case.execute("MGOMEZ@SUR", "correcta")
    claims = tokens.decode(pair.access_token)

    assert claims.erp_database_id == _DATABASE_B
    assert claims.user_id == 5
    assert claims.sub == f"{_DATABASE_B}:5"
    assert claims.purpose is TokenPurpose.ACCESS


def test_legacy_token_without_database_is_rejected() -> None:
    """Un `sub` sin base es un token anterior al multi-BD.

    Se rechaza en vez de asumir que era de la default: esa suposición es
    exactamente el cruce de identidades que este cambio elimina.
    """
    import jwt

    settings = _settings()
    legacy = jwt.encode(
        {
            "sub": "5",  # el formato viejo: solo el idUsuario
            "login": "JPEREZ",
            "purpose": "access",
            "iss": settings.jwt_issuer,
            "iat": 1780000000,
            "exp": 4070908800,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        JwtTokenService(settings).decode(legacy)


def test_token_cannot_be_issued_without_a_database() -> None:
    """Emitir un token sin base dejaría una sesión que nadie puede
    atribuir a un cliente. Falla al emitir, no al usarlo."""
    user = AuthenticatedUser(
        id=5,
        erp_database_id=None,
        login="JPEREZ",
        full_name="Juan Pérez",
        is_admin=False,
        is_active=True,
    )

    with pytest.raises(InvalidTokenError):
        JwtTokenService(_settings()).issue_access_token(user)


def test_same_user_id_in_two_databases_yields_different_subjects() -> None:
    """La colisión que motiva todo el cambio: mismo `idUsuario`, personas
    distintas, subjects distintos."""
    tokens = JwtTokenService(_settings())

    def _subject(database_id: UUID) -> str:
        user = AuthenticatedUser(
            id=5,
            erp_database_id=database_id,
            login="JPEREZ",
            full_name="Juan Pérez",
            is_admin=False,
            is_active=True,
        )
        return tokens.decode(tokens.issue_access_token(user)).sub

    assert _subject(_DATABASE_A) != _subject(_DATABASE_B)
    assert _subject(uuid4()) != _subject(_DATABASE_A)
