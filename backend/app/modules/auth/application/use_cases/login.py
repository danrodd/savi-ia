"""Use case de login.

Flujo:
1. Partir el login: `JPEREZ@NORTE` → usuario `JPEREZ`, cliente `NORTE`.
   Sin `@`, la base default.
2. Resolver la base del ERP contra la que autenticar.
3. Buscar el usuario por `login` en esa base.
4. Si no existe, la base no existe, o el usuario está deshabilitado →
   InvalidCredentialsError. No distinguimos ninguno de los casos: filtrar
   cuál falló le regala información al atacante.
5. Verificar password contra el hash (MD5 hoy).
6. Emitir access + refresh tokens con la identidad calificada.
7. Persistir el `jti` del refresh para soportar revocación en logout.
"""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.modules.auth.domain.entities import AuthenticatedUser, RefreshTokenRecord
from app.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    UserDisabledError,
)
from app.modules.auth.domain.interfaces import (
    PasswordHasher,
    RefreshTokenRepository,
    TokenService,
    UserRepositoryFactory,
)
from app.modules.auth.domain.value_objects import TokenPair

# Separador del login calificado. El código del cliente valida contra
# `^[A-Z0-9_-]{2,32}$`, que excluye el `@`, así que el último `@` es
# siempre el separador aunque el `codigo` del ERP contuviera uno.
_LOGIN_SEPARATOR = "@"

# Hash MD5 de una cadena arbitraria. Se verifica contra él en los caminos
# que no llegan a comparar una contraseña real, para no saltearse el
# trabajo del hasher.
_DUMMY_HASH = "5f4dcc3b5aa765d61d8327deb882cf99"

# Duración mínima de un login fallido, en segundos.
#
# El hash dummy solo no alcanza: MD5 es prácticamente gratis y el costo
# que domina es el viaje a la BD del ERP. Medido contra el ERP real, el
# camino "el cliente no existe" tardaba 3,4 ms y el camino "el cliente
# existe pero la contraseña está mal" 14 ms — una diferencia de 4× que
# permite enumerar los clientes registrados cronometrando respuestas.
#
# El piso iguala todos los caminos de fallo por arriba del más lento. 250
# ms deja margen sobre una consulta al ERP normal y es imperceptible para
# quien de verdad se equivocó de contraseña.
_MIN_FAILED_LOGIN_SECONDS = 0.25


def split_qualified_login(raw: str) -> tuple[str, str | None]:
    """`"JPEREZ@NORTE"` → `("JPEREZ", "NORTE")`; `"JPEREZ"` → `("JPEREZ", None)`.

    `rsplit` y no `split`: si el `codigo` del ERP llegara a contener un
    `@`, el separador válido es el último.
    """
    login = raw.strip()
    if _LOGIN_SEPARATOR not in login:
        return login, None
    user_part, _, code_part = login.rpartition(_LOGIN_SEPARATOR)
    if not user_part or not code_part:
        # `"@NORTE"` o `"JPEREZ@"` no son logins calificados válidos. Se
        # devuelve tal cual para que falle como credencial inválida y no
        # como error de formato, que distinguiría los casos.
        return login, None
    return user_part, code_part


class LoginUseCase:
    def __init__(
        self,
        user_repository_factory: UserRepositoryFactory,
        refresh_token_repository: RefreshTokenRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
    ) -> None:
        self._users = user_repository_factory
        self._refresh_tokens = refresh_token_repository
        self._hasher = password_hasher
        self._tokens = token_service

    async def execute(
        self, login: str, password: str
    ) -> tuple[TokenPair, AuthenticatedUser]:
        started_at = time.perf_counter()
        try:
            return await self._authenticate(login, password)
        except InvalidCredentialsError:
            # Todos los caminos de fallo tardan lo mismo: sin esto, "el
            # cliente no existe" responde 4× más rápido que "la contraseña
            # está mal" y esa diferencia permite enumerar clientes.
            await _wait_until_floor(started_at)
            raise

    async def _authenticate(
        self, login: str, password: str
    ) -> tuple[TokenPair, AuthenticatedUser]:
        raw_login, database_code = split_qualified_login(login)

        repository = await self._users.for_code(database_code)
        if repository is None:
            # El cliente no existe, está desactivado o tiene credenciales
            # ilegibles. Se responde igual que ante una contraseña mala
            # para que no se pueda enumerar clientes desde el login.
            self._hasher.verify(password, _DUMMY_HASH)
            raise InvalidCredentialsError

        # Normalizamos a mayúsculas porque el `codigo` del ERP está así.
        found = await repository.find_by_login(raw_login.strip().upper())
        if found is None:
            self._hasher.verify(password, _DUMMY_HASH)
            raise InvalidCredentialsError
        if not self._hasher.verify(password, found.password_hash):
            raise InvalidCredentialsError
        if not found.user.is_active:
            # Distinguimos "deshabilitado" para que el frontend pueda
            # mostrar "tu cuenta está suspendida" en lugar de "credencial
            # inválida" — y el log también lo registra distinto.
            #
            # No pasa por el piso de duración: para llegar acá hay que
            # haber acertado la contraseña, así que no revela nada que el
            # atacante no supiera ya.
            raise UserDisabledError

        return await self._issue(found.user)

    async def _issue(
        self, user: AuthenticatedUser
    ) -> tuple[TokenPair, AuthenticatedUser]:
        access = self._tokens.issue_access_token(user)

        jti = uuid4()
        now = datetime.now(UTC)
        expires_at = now + timedelta(
            seconds=self._tokens.refresh_token_lifetime_seconds()
        )
        refresh = self._tokens.issue_refresh_token(
            user, jti=jti, expires_at=expires_at
        )
        await self._refresh_tokens.save(
            RefreshTokenRecord(
                jti=jti,
                user_id=user.id,
                # La base va en el registro: sin ella, dos usuarios con el
                # mismo `idUsuario` en clientes distintos compartirían
                # revocaciones.
                erp_database_id=_require_database(user.erp_database_id),
                user_login=user.login,
                expires_at=expires_at,
                created_at=now,
            )
        )

        pair = TokenPair(
            access_token=access,
            refresh_token=refresh,
            access_token_expires_in=self._tokens.access_token_ttl_seconds(),
        )
        return pair, user


async def _wait_until_floor(started_at: float) -> None:
    """Duerme lo que falte para llegar al piso de duración.

    `asyncio.sleep` y no `time.sleep`: bloquear el event loop haría que
    un puñado de logins fallidos concurrentes congelara todo el servidor,
    convirtiendo una mitigación en una denegación de servicio.
    """
    remaining = _MIN_FAILED_LOGIN_SECONDS - (time.perf_counter() - started_at)
    if remaining > 0:
        await asyncio.sleep(remaining)


def _require_database(database_id: UUID | None) -> UUID:
    if database_id is None:
        raise InvalidCredentialsError
    return database_id
