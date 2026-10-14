from __future__ import annotations

import json
import zlib
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.dependencies import get_clock, ingest_instance, transaction
from app.modules.clients.infrastructure import SqlAlchemyClientRepository
from app.modules.ingest.application import IngestBatchUseCase
from app.modules.ingest.infrastructure import SqlAlchemyIngestRepository
from app.modules.instances.domain import Instance
from app.shared.http_errors import ApiError
from app.shared.sync_v1 import (
    MAX_BATCH_EVENTS,
    MAX_INGEST_BYTES,
    IngestRequest,
    IngestResponse,
)

router = APIRouter(prefix="/api/v1/instances", tags=["ingest"])


def _too_large() -> ApiError:
    return ApiError(
        413,
        "batch_too_large",
        f"El lote supera {MAX_BATCH_EVENTS} eventos o {MAX_INGEST_BYTES // (1024 * 1024)} MB.",
    )


def _invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_envelope", message)


async def _read_body(request: Request) -> bytes:
    """Cuerpo descomprimido, con tope de 5 MB tanto en el cable como ya descomprimido."""
    encoding = request.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in ("identity", "gzip"):
        raise ApiError(415, "unsupported_encoding", "Content-Encoding admitido: gzip.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_INGEST_BYTES:
        raise _too_large()
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_INGEST_BYTES:
            raise _too_large()
    if encoding == "identity":
        return bytes(raw)
    # Descompresión acotada: una bomba de compresión se corta al pasar el tope.
    inflater = zlib.decompressobj(wbits=zlib.MAX_WBITS | 16)
    try:
        data = inflater.decompress(bytes(raw), MAX_INGEST_BYTES + 1)
    except zlib.error as exc:
        raise _invalid("El cuerpo no es un gzip válido.") from exc
    if len(data) > MAX_INGEST_BYTES or inflater.unconsumed_tail:
        raise _too_large()
    if not inflater.eof:
        raise _invalid("El cuerpo gzip está truncado.")
    return data


def _parse_envelope(data: bytes) -> IngestRequest:
    try:
        parsed: Any = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise _invalid("El cuerpo no es JSON UTF-8 válido.") from exc
    if not isinstance(parsed, dict):
        raise _invalid("El cuerpo debe ser un objeto JSON.")
    events = parsed.get("events")  # type: ignore[reportUnknownMemberType]
    if isinstance(events, list) and len(events) > MAX_BATCH_EVENTS:  # type: ignore[reportUnknownArgumentType]
        raise _too_large()
    try:
        return IngestRequest.model_validate(parsed)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) or "body" for e in exc.errors()})
        raise _invalid("El sobre no cumple el contrato: " + ", ".join(fields)) from exc


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: Request, instance: Instance = Depends(ingest_instance)) -> IngestResponse:
    envelope = _parse_envelope(await _read_body(request))
    async with transaction(request) as session:
        outcome = await IngestBatchUseCase(
            SqlAlchemyIngestRepository(session),
            get_clock(request),
            SqlAlchemyClientRepository(session),
        ).execute(instance, envelope)
    return IngestResponse(
        accepted=outcome.accepted, duplicates=outcome.duplicates, rejected=outcome.rejected
    )
