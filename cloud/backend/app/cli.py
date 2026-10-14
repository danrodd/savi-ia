"""`cloud-admin`: administración de SAVI Cloud hasta que exista la consola (Fase 3).

Opera directo sobre la BD configurada (`CLOUD_DATABASE_URL`). No expone HTTP.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.modules.clients.application import CreateClientUseCase, ListClientsUseCase
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.enrollments.application import (
    CreateEnrollmentTokenUseCase,
    ListEnrollmentTokensUseCase,
    RevokeEnrollmentTokenUseCase,
)
from app.modules.enrollments.infrastructure import SqlAlchemyEnrollmentTokenRepository
from app.modules.instances.application import ListInstancesUseCase
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.shared.clock import utc_now
from app.shared.errors import DomainError


def _fmt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S UTC") if value else "-"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    widths = [
        max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)
    ]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    for row in rows:
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloud-admin", description="Administración de SAVI Cloud")
    sub = parser.add_subparsers(dest="group", required=True)

    client = sub.add_parser("client", help="clientes (empresas)").add_subparsers(
        dest="action", required=True
    )
    create = client.add_parser("create", help="crear un cliente")
    create.add_argument("--code", required=True, help="[A-Z0-9_]{2,32}, único")
    create.add_argument("--name", required=True)
    create.add_argument("--nit")
    client.add_parser("list", help="listar clientes")

    token = sub.add_parser("token", help="tokens de vinculación").add_subparsers(
        dest="action", required=True
    )
    tcreate = token.add_parser("create", help="crear un token (se imprime una sola vez)")
    tcreate.add_argument("--client", required=True, help="código del cliente")
    tcreate.add_argument("--expires-hours", type=int, default=None, help="vigencia (def. 72)")
    tlist = token.add_parser("list", help="listar tokens de un cliente")
    tlist.add_argument("--client", required=True)
    trevoke = token.add_parser("revoke", help="revocar un token pendiente")
    trevoke.add_argument("token_id", type=UUID)

    instance = sub.add_parser("instance", help="instancias vinculadas").add_subparsers(
        dest="action", required=True
    )
    ilist = instance.add_parser("list", help="listar instancias de un cliente")
    ilist.add_argument("--client", required=True)
    return parser


async def _run(args: argparse.Namespace, settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        # Una transacción por comando: si el caso de uso falla, no queda nada a medias.
        async with sessionmaker() as session, session.begin():
            await _dispatch(args, session, settings)
    finally:
        await engine.dispose()


async def _dispatch(args: argparse.Namespace, session: AsyncSession, settings: Settings) -> None:
    clients = SqlAlchemyClientRepository(session)
    tokens = SqlAlchemyEnrollmentTokenRepository(session)
    instances = SqlAlchemyInstanceRepository(session)
    key = (str(args.group), str(args.action))

    if key == ("client", "create"):
        client = await CreateClientUseCase(clients, utc_now).execute(
            code=str(args.code), name=str(args.name), nit=args.nit
        )
        print(f"Cliente creado: {client.code} ({client.name}) id={client.id}")
    elif key == ("client", "list"):
        rows = await ListClientsUseCase(clients).execute()
        _table(
            ["CODE", "NAME", "STATUS", "ID"],
            [[c.code, c.name, c.status.value, str(c.id)] for c in rows],
        )
    elif key == ("token", "create"):
        created = await CreateEnrollmentTokenUseCase(
            clients,
            tokens,
            utc_now,
            default_expires_hours=settings.enrollment_token_ttl_hours,
        ).execute(client_code=str(args.client), expires_hours=args.expires_hours)
        print(
            f"Token {created.token.id} creado para {args.client}; "
            f"vence {_fmt(created.token.expires_at)}. Se muestra UNA sola vez:",
            file=sys.stderr,
        )
        print(created.plaintext)
    elif key == ("token", "list"):
        now = utc_now()
        rows_t = await ListEnrollmentTokensUseCase(clients, tokens).execute(str(args.client))
        _table(
            ["ID", "STATE", "EXPIRES", "USED", "CREATED"],
            [
                [
                    str(t.id),
                    t.state(now).value,
                    _fmt(t.expires_at),
                    _fmt(t.used_at),
                    _fmt(t.created_at),
                ]
                for t in rows_t
            ],
        )
    elif key == ("token", "revoke"):
        revoked = await RevokeEnrollmentTokenUseCase(tokens, utc_now).execute(args.token_id)
        print(f"Token {revoked.id} revocado.")
    elif key == ("instance", "list"):
        rows_i = await ListInstancesUseCase(clients, instances).execute(str(args.client))
        _table(
            ["ID", "NAME", "STATUS", "VERSION", "LAST_SEEN", "ENROLLED"],
            [
                [
                    str(i.id),
                    i.name,
                    i.status.value,
                    i.version or "-",
                    _fmt(i.last_seen_at),
                    _fmt(i.enrolled_at),
                ]
                for i in rows_i
            ],
        )
    else:  # pragma: no cover - argparse ya lo impide
        raise SystemExit(f"Comando no soportado: {key}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"error: configuración inválida: {exc.errors()[0]['msg']}", file=sys.stderr)
        return 2
    try:
        asyncio.run(_run(args, settings))
    except DomainError as exc:
        print(f"error: {exc.code}: {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
