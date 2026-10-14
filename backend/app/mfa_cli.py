"""Restablece el segundo factor desde la línea de comandos.

Es la salida de emergencia: si el único administrador pierde el celular, nadie puede entrar a
Administración para restablecerlo. Quien opera el servidor lo hace desde acá:

    docker compose exec savi /app/docker-entrypoint.sh python -m app.mfa_cli reset JPEREZ@NORTE

Corre con la configuración y las claves del propio servidor, así que no necesita sesión.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from app.infrastructure.config import get_settings
from app.infrastructure.database import close_engines, get_agent_sessionmaker, init_engines
from app.modules.auth.application.use_cases import ResetMfaUseCase
from app.modules.auth.infrastructure.persistence import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyTotpRepository,
)
from app.modules.erp_databases.infrastructure.persistence import SqlAlchemyErpDatabaseRepository
from app.shared.security import FernetCredentialCipher


class _Databases:
    def __init__(self, repository: SqlAlchemyErpDatabaseRepository) -> None:
        self._repository = repository

    async def database_id_for(self, code: str | None):  # type: ignore[no-untyped-def]
        database = (
            await self._repository.get_default()
            if code is None
            else await self._repository.get_by_code(code.strip().upper())
        )
        return database.id if database is not None else None


async def _reset(login: str) -> bool:
    settings = get_settings()
    init_engines(settings)
    try:
        sessionmaker = get_agent_sessionmaker()
        cipher = FernetCredentialCipher(
            settings.erp_credentials_key, old_keys=[settings.erp_credentials_key_old]
        )
        use_case = ResetMfaUseCase(
            SqlAlchemyTotpRepository(sessionmaker, cipher),
            SqlAlchemyRefreshTokenRepository(sessionmaker),
            _Databases(SqlAlchemyErpDatabaseRepository(sessionmaker, cipher)),
        )
        return await use_case.execute(login)
    finally:
        await close_engines()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.mfa_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    reset = sub.add_parser("reset", help="restablecer el segundo factor de un usuario")
    reset.add_argument("login", help="login del ERP, con cliente si hace falta: JPEREZ@NORTE")
    args = parser.parse_args(argv)

    if args.command == "reset":
        done = asyncio.run(_reset(str(args.login)))
        if done:
            print(f"Segundo factor restablecido para {args.login}. Sus sesiones se cerraron.")
            return 0
        print(f"{args.login} no tenía segundo factor (o el usuario o el cliente no existe).")
        return 1
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
