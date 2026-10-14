"""Consultas de lectura de la consola (modelo de lectura, sin reglas de negocio)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.domain import Client, ClientStatus
from app.modules.clients.infrastructure import ClientModel
from app.modules.clients.infrastructure import to_entity as client_entity
from app.modules.instances.domain import Instance
from app.modules.instances.infrastructure import (
    HeartbeatModel,
    InstanceModel,
)
from app.modules.instances.infrastructure import (
    to_entity as instance_entity,
)
from app.shared.clock import Clock, as_utc

# Una instancia está "online" si habló hace menos de esto (§4.1).
ONLINE_WINDOW = timedelta(minutes=15)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def version_key(version: str | None) -> tuple[int, int, int] | None:
    """`v1.2.3` (o `1.2.3-4-gabc`) -> (1, 2, 3). `None` si no tiene forma de versión."""
    if not version:
        return None
    match = _VERSION.match(version.strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def is_outdated(version: str | None, latest: str | None) -> bool:
    current, newest = version_key(version), version_key(latest)
    return current is not None and newest is not None and current < newest


def is_online(last_seen_at: datetime | None, now: datetime) -> bool:
    return last_seen_at is not None and now - last_seen_at < ONLINE_WINDOW


@dataclass(frozen=True)
class ClientSummary:
    client: Client
    instances_total: int
    instances_online: int
    last_seen_at: datetime | None
    oldest_version: str | None


@dataclass(frozen=True)
class InstanceListItem:
    instance: Instance
    client_code: str
    client_name: str
    online: bool
    outdated: bool


@dataclass(frozen=True)
class HeartbeatItem:
    id: UUID
    received_at: datetime
    payload: dict[str, Any]


class ConsoleQueries:
    def __init__(self, session: AsyncSession, clock: Clock, latest_version: str = "") -> None:
        self._session = session
        self._clock = clock
        self._latest = latest_version or None

    # --- clientes

    async def list_clients(
        self,
        *,
        status: ClientStatus | None = None,
        q: str | None = None,
        sort: str = "code",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ClientSummary], int]:
        stmt = select(ClientModel)
        if status is not None:
            stmt = stmt.where(ClientModel.status == status.value)
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(ClientModel.code).like(like), func.lower(ClientModel.name).like(like)
                )
            )
        clients = [client_entity(m) for m in (await self._session.execute(stmt)).scalars()]
        summaries = await self._summaries(clients)
        if sort == "last_seen":
            summaries.sort(key=lambda s: s.last_seen_at or _EPOCH, reverse=True)
        elif sort == "name":
            summaries.sort(key=lambda s: s.client.name.lower())
        else:
            summaries.sort(key=lambda s: s.client.code)
        total = len(summaries)
        return summaries[offset : offset + limit], total

    async def client_summary(self, client_id: UUID) -> ClientSummary | None:
        model = await self._session.get(ClientModel, client_id)
        if model is None:
            return None
        return (await self._summaries([client_entity(model)]))[0]

    async def _summaries(self, clients: list[Client]) -> list[ClientSummary]:
        if not clients:
            return []
        ids = [c.id for c in clients]
        rows = (
            await self._session.execute(
                select(InstanceModel).where(InstanceModel.client_id.in_(ids))
            )
        ).scalars()
        by_client: dict[UUID, list[Instance]] = {}
        for model in rows:
            by_client.setdefault(model.client_id, []).append(instance_entity(model))
        now = self._clock()
        out: list[ClientSummary] = []
        for client in clients:
            instances = by_client.get(client.id, [])
            seen = [i.last_seen_at for i in instances if i.last_seen_at is not None]
            versions = [
                (key, i.version) for i in instances if (key := version_key(i.version)) is not None
            ]
            out.append(
                ClientSummary(
                    client=client,
                    instances_total=len(instances),
                    instances_online=sum(is_online(i.last_seen_at, now) for i in instances),
                    last_seen_at=max(seen) if seen else None,
                    oldest_version=min(versions)[1] if versions else None,
                )
            )
        return out

    # --- instancias

    async def list_instances(
        self,
        *,
        client_id: UUID | None = None,
        status: str | None = None,
        connectivity: str | None = None,
        version: str | None = None,
        outdated: bool | None = None,
    ) -> list[InstanceListItem]:
        stmt = select(InstanceModel, ClientModel.code, ClientModel.name).join(
            ClientModel, ClientModel.id == InstanceModel.client_id
        )
        if client_id is not None:
            stmt = stmt.where(InstanceModel.client_id == client_id)
        if status:
            stmt = stmt.where(InstanceModel.status == status)
        if version:
            stmt = stmt.where(InstanceModel.version == version)
        stmt = stmt.order_by(ClientModel.code, InstanceModel.name)
        now = self._clock()
        items: list[InstanceListItem] = []
        for model, code, name in (await self._session.execute(stmt)).all():
            instance = instance_entity(model)
            online = is_online(instance.last_seen_at, now)
            old = is_outdated(instance.version, self._latest)
            if connectivity == "online" and not online:
                continue
            if connectivity == "offline" and online:
                continue
            if outdated is True and not old:
                continue
            items.append(InstanceListItem(instance, code, name, online, old))
        return items

    async def get_instance(self, instance_id: UUID) -> InstanceListItem | None:
        row = (
            await self._session.execute(
                select(InstanceModel, ClientModel.code, ClientModel.name)
                .join(ClientModel, ClientModel.id == InstanceModel.client_id)
                .where(InstanceModel.id == instance_id)
            )
        ).first()
        if row is None:
            return None
        model, code, name = row
        instance = instance_entity(model)
        return InstanceListItem(
            instance,
            code,
            name,
            is_online(instance.last_seen_at, self._clock()),
            is_outdated(instance.version, self._latest),
        )

    async def list_heartbeats(
        self,
        instance_id: UUID,
        *,
        limit: int,
        before: tuple[datetime, UUID] | None,
    ) -> list[HeartbeatItem]:
        stmt = select(HeartbeatModel).where(HeartbeatModel.instance_id == instance_id)
        if before is not None:
            at, hb_id = before
            stmt = stmt.where(
                or_(
                    HeartbeatModel.received_at < at,
                    and_(HeartbeatModel.received_at == at, HeartbeatModel.id < hb_id),
                )
            )
        stmt = stmt.order_by(HeartbeatModel.received_at.desc(), HeartbeatModel.id.desc()).limit(
            limit
        )
        rows = (await self._session.execute(stmt)).scalars()
        return [HeartbeatItem(m.id, as_utc(m.received_at), m.payload) for m in rows]
