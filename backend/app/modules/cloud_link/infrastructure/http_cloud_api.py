"""Cliente HTTP de SAVI Cloud (`/api/v1`) con `httpx`.

- Timeouts: conexión 10 s, lectura 30 s.
- `trust_env=True`: respeta `HTTPS_PROXY` corporativo (RNF-02).
- Validación TLS siempre activa. `http://` solo con `allow_insecure_http`
  (`APP_ENV=development`).
- Los errores salen como `CloudApiError` con un **código corto**; el mensaje
  libre de Cloud no se guarda ni se loguea.
- Nunca se loguean el bearer ni el cuerpo de los pedidos.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from app.modules.cloud_link.domain.entities import CloudNotice, iso_utc
from app.modules.cloud_link.domain.exceptions import CloudApiError, InsecureCloudUrlError
from app.modules.cloud_link.domain.interfaces import (
    CloudApi,
    EnrollResult,
    HeartbeatResult,
    IngestResult,
    JsonObject,
    RejectedEvent,
)
from app.modules.cloud_link.domain.value_objects import AccessRules, AiLimits, SyncPolicy
from app.modules.cloud_link.infrastructure import contract_v1 as contract

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 30.0
_API_PREFIX = "/api/v1"
_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,64}$")

_DEFAULT_CODES = {
    401: "instance_unauthorized",
    403: "forbidden",
    404: "not_found",
    413: "batch_too_large",
    422: "validation_error",
    429: "too_many_requests",
}


def _error_code(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code: Any = body.get("errorCode")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(code, str) and _ERROR_CODE.match(code):
            return code
    status = response.status_code
    if status >= 500:
        return "cloud_unavailable"
    return _DEFAULT_CODES.get(status, f"http_{status}")


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(float(raw.strip()), 0.0)
    except ValueError:
        return None  # fecha HTTP: no se interpreta, se usa el backoff propio


def _ai_limits(model: contract.AiPolicy | None) -> AiLimits | None:
    if model is None:
        return None
    return AiLimits(
        allowed_providers=(
            frozenset(model.allowed_providers) if model.allowed_providers is not None else None
        ),
        user_monthly_usd=(
            Decimal(model.user_monthly_usd) if model.user_monthly_usd is not None else None
        ),
        provider_monthly_usd={k: Decimal(v) for k, v in model.provider_monthly_usd.items()},
        user_overrides={k: Decimal(v) for k, v in model.user_overrides.items()},
    )


def _access_rules(model: contract.AccessPolicy | None) -> AccessRules | None:
    if model is None:
        return None
    return AccessRules(
        default_databases=(
            frozenset(UUID(r) for r in model.default_databases)
            if model.default_databases is not None
            else None
        ),
        user_databases={
            k: frozenset(UUID(r) for r in refs) for k, refs in model.user_databases.items()
        },
    )


def _policy(model: contract.Policy) -> SyncPolicy:
    return SyncPolicy(
        heartbeat_seconds=model.heartbeat_seconds,
        ingest_seconds=model.ingest_seconds,
        max_batch_events=model.max_batch_events,
        sync_enabled=model.sync_enabled,
        config_locked=model.config_locked,
        allow_local_cli=model.allow_local_cli,
        ai=_ai_limits(model.ai),
        access=_access_rules(model.access),
        identity_mode=model.identity_mode,
    )


class HttpxCloudApi(CloudApi):
    def __init__(
        self,
        *,
        allow_insecure_http: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._allow_insecure_http = allow_insecure_http
        self._transport = transport

    # ── CloudApi ─────────────────────────────────────────────────────────

    async def enroll(self, *, cloud_url: str, token: str, instance: JsonObject) -> EnrollResult:
        response = await self._post(
            cloud_url, "/enrollments/redeem", json_body={"token": token, "instance": instance}
        )
        body = self._parse(response, contract.EnrollResponse)
        return EnrollResult(
            instance_id=UUID(body.instance_id),
            instance_secret=body.instance_secret,
            client_code=body.client.code,
            client_name=body.client.name,
            policy=_policy(body.policy),
        )

    async def heartbeat(
        self, *, cloud_url: str, secret: str, payload: JsonObject
    ) -> HeartbeatResult:
        response = await self._post(
            cloud_url, "/instances/heartbeat", secret=secret, json_body=payload
        )
        body = self._parse(response, contract.HeartbeatResponse)
        return HeartbeatResult(
            instance_status=body.instance_status,
            policy=_policy(body.policy),
            notices=[CloudNotice(n.code, n.severity, n.message) for n in body.notices],
        )

    async def ingest(
        self,
        *,
        cloud_url: str,
        secret: str,
        batch_id: str,
        sent_at: datetime,
        events: Sequence[JsonObject],
    ) -> IngestResult:
        raw = json.dumps(
            {"batch_id": batch_id, "sent_at": iso_utc(sent_at), "events": list(events)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(raw) > contract.MAX_INGEST_BYTES:
            # Igual que un 413 de Cloud: el caso de uso parte el lote.
            raise CloudApiError("batch_too_large", status_code=413)
        response = await self._post(
            cloud_url, "/instances/ingest", secret=secret, raw_body=gzip.compress(raw), gzipped=True
        )
        body = self._parse(response, contract.IngestResponse)
        return IngestResult(
            accepted=body.accepted,
            duplicates=body.duplicates,
            rejected=[RejectedEvent(r.source_id, r.reason) for r in body.rejected],
        )

    async def rotate(self, *, cloud_url: str, secret: str) -> str:
        response = await self._post(cloud_url, "/instances/credentials/rotate", secret=secret)
        return self._parse(response, contract.RotateResponse).instance_secret

    # ── transporte ───────────────────────────────────────────────────────

    def _url(self, cloud_url: str, path: str) -> str:
        base = cloud_url.strip().rstrip("/")
        if base.startswith("http://") and not self._allow_insecure_http:
            raise InsecureCloudUrlError
        if not (base.startswith("https://") or base.startswith("http://")):
            raise InsecureCloudUrlError
        return f"{base}{_API_PREFIX}{path}"

    async def _post(
        self,
        cloud_url: str,
        path: str,
        *,
        secret: str | None = None,
        json_body: JsonObject | None = None,
        raw_body: bytes | None = None,
        gzipped: bool = False,
    ) -> httpx.Response:
        url = self._url(cloud_url, path)
        headers: dict[str, str] = {"Accept": "application/json"}
        if secret is not None:
            headers["Authorization"] = f"Bearer {secret}"
        content: bytes | None = raw_body
        if json_body is not None:
            content = json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode()
        if content is not None:
            headers["Content-Type"] = "application/json"
        if gzipped:
            headers["Content-Encoding"] = "gzip"

        timeout = httpx.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, trust_env=True, transport=self._transport
            ) as client:
                response = await client.post(url, content=content, headers=headers)
        except httpx.TimeoutException:
            raise CloudApiError("timeout") from None
        except httpx.HTTPError:
            # DNS, conexión rechazada, TLS inválido, proxy: todo "sin conexión".
            raise CloudApiError("network_error") from None

        if response.status_code >= 400:
            raise CloudApiError(
                _error_code(response),
                status_code=response.status_code,
                retry_after_seconds=_retry_after(response),
            )
        return response

    @staticmethod
    def _parse[T: BaseModel](response: httpx.Response, model: type[T]) -> T:
        try:
            return model.model_validate(response.json())
        except (ValueError, ValidationError):
            # 2xx con un cuerpo que no cumple el contrato: no se puede
            # interpretar. Sin `status_code`, así que cuenta como transitorio
            # y se reintenta con backoff.
            logger.warning("Respuesta de SAVI Cloud fuera del contrato (%s).", model.__name__)
            raise CloudApiError("invalid_response") from None
