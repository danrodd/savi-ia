from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.dependencies import authenticated_instance, get_clock, heartbeat_instance, transaction
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.instances.application import RecordHeartbeatUseCase, RotateCredentialsUseCase
from app.modules.instances.domain import Instance
from app.modules.instances.infrastructure import (
    SqlAlchemyHeartbeatRepository,
    SqlAlchemyInstanceRepository,
)
from app.shared.sync_v1 import HeartbeatRequest, HeartbeatResponse, RotateResponse

router = APIRouter(prefix="/api/v1/instances", tags=["instances"])


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    body: HeartbeatRequest,
    request: Request,
    instance: Instance = Depends(heartbeat_instance),
) -> HeartbeatResponse:
    async with transaction(request) as session:
        return await RecordHeartbeatUseCase(
            SqlAlchemyInstanceRepository(session),
            SqlAlchemyHeartbeatRepository(session),
            get_clock(request),
            SqlAlchemyClientRepository(session),
        ).execute(instance.id, body)


@router.post("/credentials/rotate", response_model=RotateResponse)
async def rotate_credentials(
    request: Request, instance: Instance = Depends(authenticated_instance)
) -> RotateResponse:
    """Secreto nuevo; el anterior sigue valiendo 24 h (§3.4)."""
    async with transaction(request) as session:
        secret = await RotateCredentialsUseCase(
            SqlAlchemyInstanceRepository(session), get_clock(request)
        ).execute(instance.id)
    return RotateResponse(instance_secret=secret)
