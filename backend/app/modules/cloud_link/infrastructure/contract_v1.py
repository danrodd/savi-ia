"""Modelos Pydantic del contrato `contracts/sync/v1/`, escritos a mano.

Espejo de los JSON Schema (`contracts/sync/v1/`): un test de contrato valida los
mismos fixtures contra ambos. Mismo criterio que el lado Cloud, pero este
archivo es propio de la instancia y no importa nada de `cloud/`.

Reglas (ver `contracts/sync/v1/README.md`):

- Los sobres ignoran los campos desconocidos (`extra="ignore"`): agregar campos
  opcionales es compatible dentro de v1.
- `data` de cada evento es una lista blanca estricta (`extra="forbid"`): nunca
  viaja contenido.
- Sin coerción: un entero no se acepta como texto ni al revés, igual que el
  JSON Schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
)

MAX_BATCH_EVENTS = 500
MAX_INGEST_BYTES = 5 * 1024 * 1024

_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _require_text(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("debe ser una fecha ISO-8601 en texto")
    return value


def _text(
    *, min_length: int = 0, max_length: int | None = None, pattern: str | None = None
) -> StringConstraints:
    return StringConstraints(
        strict=True, min_length=min_length, max_length=max_length, pattern=pattern
    )


# Fecha ISO-8601 con zona (naive se rechaza), siempre como texto.
IsoDatetime = Annotated[AwareDatetime, BeforeValidator(_require_text)]
UuidStr = Annotated[str, _text(pattern=_UUID_PATTERN)]
NonNegInt = Annotated[StrictInt, Field(ge=0)]
Name200 = Annotated[str, _text(min_length=1, max_length=200)]
Short64 = Annotated[str, _text(max_length=64)]
Short128 = Annotated[str, _text(max_length=128)]
Code64 = Annotated[str, _text(pattern=r"^[a-z0-9_]{1,64}$")]
DeploymentMode = Literal["server", "desktop"]


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Policy(_Envelope):
    heartbeat_seconds: Annotated[StrictInt, Field(ge=1)]
    ingest_seconds: Annotated[StrictInt, Field(ge=1)]
    max_batch_events: Annotated[StrictInt, Field(ge=1, le=MAX_BATCH_EVENTS)]
    sync_enabled: StrictBool
    config_locked: StrictBool = False
    allow_local_cli: StrictBool = False
    identity_mode: Literal["pseudonym", "named"] = "pseudonym"


# --- enroll -----------------------------------------------------------------------------


class EnrollInstance(_Envelope):
    name: Name200
    deployment_mode: DeploymentMode
    version: Short64 | None = None
    commit: Short64 | None = None
    os: Name200
    agent_db_engine: Literal["postgresql", "sqlite"]
    fingerprint: Annotated[str, _text(min_length=1, max_length=128)]


class EnrollRequest(_Envelope):
    token: Annotated[str, _text(min_length=1, max_length=256)]
    instance: EnrollInstance


class EnrollClient(_Envelope):
    id: UuidStr
    code: Annotated[str, _text(min_length=2, max_length=32)]
    name: Name200


class EnrollResponse(_Envelope):
    instance_id: UuidStr
    instance_secret: Annotated[str, _text(pattern=r"^svk_ins_[0-9A-Za-z]{43}$")]
    client: EnrollClient
    policy: Policy


# --- heartbeat --------------------------------------------------------------------------


class HeartbeatLlm(_Envelope):
    provider: Short64 | None = None
    model: Short128 | None = None
    credential_kind: Short64 | None = None
    usable: StrictBool | None = None


class HeartbeatErpDatabases(_Envelope):
    total: NonNegInt = 0
    usable: NonNegInt = 0
    credentials_unreadable: NonNegInt = 0


class HeartbeatStream(_Envelope):
    watermark_at: IsoDatetime | None = None
    last_ok_at: IsoDatetime | None = None


class HeartbeatSync(_Envelope):
    streams: dict[str, HeartbeatStream] = Field(default_factory=dict)
    last_error: Short64 | None = None


class HeartbeatRequest(_Envelope):
    sent_at: IsoDatetime
    fingerprint: Annotated[str, _text(min_length=1, max_length=128)]
    version: Short64 | None
    commit: Short64 | None = None
    deployment_mode: DeploymentMode
    started_at: IsoDatetime | None = None
    tls: StrictBool | None = None
    llm: HeartbeatLlm | None = None
    erp_databases: HeartbeatErpDatabases | None = None
    active_sessions: NonNegInt | None = None
    sync: HeartbeatSync | None = None
    warnings: Annotated[list[Code64], Field(max_length=50)] = Field(default_factory=list)


class Notice(_Envelope):
    code: Code64
    severity: Literal["info", "warning", "critical"]
    message: Annotated[str, _text(max_length=500)]


class HeartbeatResponse(_Envelope):
    server_time: datetime
    instance_status: Literal["active", "suspended", "revoked"]
    policy: Policy
    notices: list[Notice]
    ai: dict[str, Any] | None = None


# --- ingest -----------------------------------------------------------------------------


class IngestRequest(_Envelope):
    batch_id: UuidStr
    sent_at: IsoDatetime
    events: Annotated[list[dict[str, Any]], Field(max_length=MAX_BATCH_EVENTS)]


class RejectedEvent(_Envelope):
    source_id: Annotated[str, _text(max_length=128)]
    reason: Literal["unknown_schema", "invalid_event"]


class IngestResponse(_Envelope):
    accepted: NonNegInt
    duplicates: NonNegInt
    rejected: list[RejectedEvent]


class RotateResponse(_Envelope):
    instance_secret: str


# --- eventos (lista blanca estricta) ----------------------------------------------------


class ToolInvocation(_Strict):
    name: Annotated[str, _text(min_length=1, max_length=100)]
    status: Annotated[str, _text(min_length=1, max_length=32)]
    tipo: Code64 | None = None


class TurnData(_Strict):
    conversation_ref: UuidStr
    database_ref: UuidStr | None = None
    user_ref: Annotated[str, _text(pattern=r"^[0-9a-f]{32}$")]
    provider: Short64 | None = None
    model: Short128 | None = None
    finish_reason: Short64 | None = None
    input_tokens: NonNegInt
    output_tokens: NonNegInt
    cache_read_input_tokens: NonNegInt
    cache_creation_input_tokens: NonNegInt
    cost_usd: Annotated[str, _text(pattern=r"^[0-9]{1,6}(\.[0-9]{1,6})?$")] | None = None
    tools: Annotated[list[ToolInvocation], Field(max_length=100)] = Field(
        default_factory=list[ToolInvocation]
    )
    latency_ms: NonNegInt | None = None
    action: Literal["send", "edit_last", "regenerate"] | None = None


class ConversationData(_Strict):
    conversation_ref: UuidStr
    database_ref: UuidStr | None = None
    user_ref: Annotated[str, _text(pattern=r"^[0-9a-f]{32}$")]


class SessionData(_Strict):
    user_ref: Annotated[str, _text(pattern=r"^[0-9a-f]{32}$")]
    user_label: Annotated[str, _text(min_length=1, max_length=64)] | None = None
    database_ref: UuidStr | None = None


class FreeQueryData(_Strict):
    conversation_ref: UuidStr | None = None
    database_ref: UuidStr | None = None
    result: Annotated[str, _text(pattern=r"^[a-z0-9_]{1,32}$")]
    estimated_rows: NonNegInt | None = None
    returned_rows: NonNegInt | None = None
    duration_ms: NonNegInt | None = None


class DatabaseData(_Strict):
    database_ref: UuidStr
    code: Annotated[str, _text(min_length=1, max_length=64)]
    name: Name200
    is_active: StrictBool
    is_usable: StrictBool
    credentials_unreadable: StrictBool
    last_connection_ok_at: IsoDatetime | None = None


class _Event(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    source_id: Annotated[str, _text(min_length=1, max_length=128)]
    occurred_at: IsoDatetime


class TurnEvent(_Event):
    schema_: Literal["turn/1"] = Field(alias="schema")
    data: TurnData


class ConversationEvent(_Event):
    schema_: Literal["conversation/1"] = Field(alias="schema")
    data: ConversationData


class SessionEvent(_Event):
    schema_: Literal["session/1"] = Field(alias="schema")
    data: SessionData


class FreeQueryEvent(_Event):
    schema_: Literal["free_query/1"] = Field(alias="schema")
    data: FreeQueryData


class DatabaseEvent(_Event):
    schema_: Literal["database/1"] = Field(alias="schema")
    data: DatabaseData


type AnyEvent = TurnEvent | ConversationEvent | SessionEvent | FreeQueryEvent | DatabaseEvent

# Valor de `schema` -> modelo del evento completo.
EVENT_MODELS: dict[str, type[AnyEvent]] = {
    "turn/1": TurnEvent,
    "conversation/1": ConversationEvent,
    "session/1": SessionEvent,
    "free_query/1": FreeQueryEvent,
    "database/1": DatabaseEvent,
}
