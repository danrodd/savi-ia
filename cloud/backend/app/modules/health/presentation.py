from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: no toca la BD."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def ready(request: Request) -> Any:
    """Readiness: verifica que la BD responde."""
    engine: AsyncEngine = request.app.state.engine
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - cualquier fallo de BD significa "no listo"
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}
