from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_clock, limit_redeem, transaction
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.enrollments.application import RedeemEnrollmentTokenUseCase
from app.modules.enrollments.domain import InstanceInfo
from app.modules.enrollments.infrastructure import SqlAlchemyEnrollmentTokenRepository
from app.modules.instances.application import policy_for
from app.modules.instances.infrastructure import SqlAlchemyInstanceRepository
from app.shared.sync_v1 import EnrollClient, EnrollRequest, EnrollResponse

router = APIRouter(prefix="/api/v1/enrollments", tags=["enrollments"])


@router.post("/redeem", status_code=201, response_model=EnrollResponse)
async def redeem(
    body: EnrollRequest, request: Request, _: None = Depends(limit_redeem)
) -> EnrollResponse:
    """Canjea un token de vinculación por `instance_id` + secreto (§3.1). Sin Bearer."""
    info = InstanceInfo(
        name=body.instance.name,
        deployment_mode=body.instance.deployment_mode,
        version=body.instance.version,
        commit=body.instance.commit,
        os=body.instance.os,
        agent_db_engine=body.instance.agent_db_engine,
        fingerprint=body.instance.fingerprint,
    )
    # Canje + creación de la instancia, en una sola transacción con el token bloqueado.
    async with transaction(request) as session:
        result = await RedeemEnrollmentTokenUseCase(
            SqlAlchemyClientRepository(session),
            SqlAlchemyEnrollmentTokenRepository(session),
            SqlAlchemyInstanceRepository(session),
            get_clock(request),
        ).execute(token=body.token, info=info)
    return EnrollResponse(
        instance_id=str(result.instance.id),
        instance_secret=result.instance_secret,
        client=EnrollClient(
            id=str(result.client.id), code=result.client.code, name=result.client.name
        ),
        policy=policy_for(result.instance.status, result.client),
    )
