from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.shared.errors import DomainError

CLIENT_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,32}$")


class ClientStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class IdentityMode(StrEnum):
    """Cómo se identifica a las personas de un cliente en Cloud."""

    # Seudónimo (HMAC): Cloud cuenta usuarios sin saber quiénes son. Es el modo de los clientes.
    PSEUDONYM = "pseudonym"
    # Código de usuario del ERP. Solo para la organización interna (SEO Group): ahí
    # "5 SAVI funcionando" tiene que poder decir de quiénes son.
    NAMED = "named"


AI_PROVIDERS = ("claude", "gemini", "openai")
_USER_REF = re.compile(r"^[0-9a-f]{32}$")
MAX_USER_OVERRIDES = 500
MAX_USD = Decimal("99999999")


class InvalidAiPolicy(DomainError):
    code = "invalid_ai_policy"


def _usd(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - cualquier valor ilegible es un monto inválido
        raise InvalidAiPolicy(f"Monto inválido: {value!r}.") from exc
    if not amount.is_finite() or amount < 0 or amount > MAX_USD:
        raise InvalidAiPolicy("El monto debe estar entre 0 y 99.999.999 USD.")
    return amount.quantize(Decimal("0.0001"))


@dataclass(frozen=True)
class AiPolicy:
    """Qué proveedores de IA pueden usar las instalaciones del cliente y cuánto pueden gastar.

    Vacía = sin límites. La decide Cloud; la instancia mide y bloquea.
    """

    # `None` = todos los proveedores.
    allowed_providers: tuple[str, ...] | None = None
    # Tope mensual por persona (USD). `None` = sin tope.
    user_monthly_usd: Decimal | None = None
    # Tope mensual de toda la instalación por proveedor (USD).
    provider_monthly_usd: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    # Tope propio de una persona (`user_ref`), en lugar del general. `0` la deja sin IA.
    user_overrides: dict[str, Decimal] = field(default_factory=dict[str, Decimal])

    @property
    def is_empty(self) -> bool:
        return (
            self.allowed_providers is None
            and self.user_monthly_usd is None
            and not self.provider_monthly_usd
            and not self.user_overrides
        )

    @classmethod
    def build(
        cls,
        *,
        allowed_providers: Sequence[str] | None,
        user_monthly_usd: object | None,
        provider_monthly_usd: Mapping[str, object],
        user_overrides: Mapping[str, object],
    ) -> AiPolicy:
        if allowed_providers is not None:
            unknown = sorted(set(allowed_providers) - set(AI_PROVIDERS))
            if unknown:
                raise InvalidAiPolicy(f"Proveedor desconocido: {', '.join(unknown)}.")
        unknown = sorted(set(provider_monthly_usd) - set(AI_PROVIDERS))
        if unknown:
            raise InvalidAiPolicy(f"Proveedor desconocido: {', '.join(unknown)}.")
        if len(user_overrides) > MAX_USER_OVERRIDES:
            raise InvalidAiPolicy(f"Máximo {MAX_USER_OVERRIDES} excepciones por cliente.")
        for ref in user_overrides:
            if not _USER_REF.fullmatch(ref):
                raise InvalidAiPolicy("Identificador de persona inválido.")
        return cls(
            allowed_providers=(
                tuple(dict.fromkeys(allowed_providers)) if allowed_providers is not None else None
            ),
            user_monthly_usd=_usd(user_monthly_usd) if user_monthly_usd is not None else None,
            provider_monthly_usd={k: _usd(v) for k, v in provider_monthly_usd.items()},
            user_overrides={k: _usd(v) for k, v in user_overrides.items()},
        )

    def to_json(self) -> dict[str, object]:
        """Forma de almacenamiento y de la API: los montos van como texto."""
        return {
            "allowed_providers": list(self.allowed_providers)
            if self.allowed_providers is not None
            else None,
            "user_monthly_usd": _fmt(self.user_monthly_usd),
            "provider_monthly_usd": {k: _fmt(v) for k, v in self.provider_monthly_usd.items()},
            "user_overrides": {k: _fmt(v) for k, v in self.user_overrides.items()},
        }

    @classmethod
    def from_json(cls, raw: dict[str, object] | None) -> AiPolicy:
        if not raw:
            return cls()
        providers = raw.get("allowed_providers")
        monthly = raw.get("user_monthly_usd")
        per_provider = raw.get("provider_monthly_usd")
        overrides = raw.get("user_overrides")
        return cls.build(
            allowed_providers=list(providers) if isinstance(providers, list) else None,  # pyright: ignore[reportUnknownArgumentType]
            user_monthly_usd=monthly,
            provider_monthly_usd=dict(per_provider) if isinstance(per_provider, dict) else {},  # pyright: ignore[reportUnknownArgumentType]
            user_overrides=dict(overrides) if isinstance(overrides, dict) else {},  # pyright: ignore[reportUnknownArgumentType]
        )


def _fmt(amount: Decimal | None) -> str | None:
    if amount is None:
        return None
    text = format(amount.normalize(), "f")
    return text if "." not in text else text.rstrip("0").rstrip(".")


_DATABASE_REF = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_DATABASES_PER_RULE = 200


class InvalidAccessPolicy(DomainError):
    code = "invalid_access_policy"


def _databases(refs: Sequence[str]) -> tuple[str, ...]:
    cleaned = tuple(dict.fromkeys(r.strip().lower() for r in refs))
    if len(cleaned) > MAX_DATABASES_PER_RULE:
        raise InvalidAccessPolicy(f"Máximo {MAX_DATABASES_PER_RULE} bases por regla.")
    for ref in cleaned:
        if not _DATABASE_REF.fullmatch(ref):
            raise InvalidAccessPolicy("Identificador de base inválido.")
    return cleaned


@dataclass(frozen=True)
class AccessPolicy:
    """Qué bases del ERP puede consultar cada persona de las instalaciones del cliente.

    Solo **restringe**: la instancia sigue exigiendo que el ERP le dé acceso a la persona.
    Vacía = sin restricción.
    """

    # Bases (`database_ref`) para toda persona sin regla propia. `None` = las que permita el ERP.
    default_databases: tuple[str, ...] | None = None
    # Regla propia de una persona (`user_ref`). Reemplaza a la general; vacía = sin ninguna base.
    user_databases: dict[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])

    @property
    def is_empty(self) -> bool:
        return self.default_databases is None and not self.user_databases

    @classmethod
    def build(
        cls,
        *,
        default_databases: Sequence[str] | None,
        user_databases: Mapping[str, Sequence[str]],
    ) -> AccessPolicy:
        if len(user_databases) > MAX_USER_OVERRIDES:
            raise InvalidAccessPolicy(f"Máximo {MAX_USER_OVERRIDES} personas con regla propia.")
        for ref in user_databases:
            if not _USER_REF.fullmatch(ref):
                raise InvalidAccessPolicy("Identificador de persona inválido.")
        return cls(
            default_databases=_databases(default_databases)
            if default_databases is not None
            else None,
            user_databases={k: _databases(v) for k, v in user_databases.items()},
        )

    def to_json(self) -> dict[str, object]:
        return {
            "default_databases": list(self.default_databases)
            if self.default_databases is not None
            else None,
            "user_databases": {k: list(v) for k, v in self.user_databases.items()},
        }

    @classmethod
    def from_json(cls, raw: dict[str, object] | None) -> AccessPolicy:
        if not raw:
            return cls()
        default = raw.get("default_databases")
        users = raw.get("user_databases")
        return cls.build(
            default_databases=list(default) if isinstance(default, list) else None,  # pyright: ignore[reportUnknownArgumentType]
            user_databases={str(k): list(v) for k, v in users.items()}  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
            if isinstance(users, dict)
            else {},
        )


@dataclass(frozen=True)
class Client:
    id: UUID
    code: str
    name: str
    nit: str | None
    status: ClientStatus
    created_at: datetime
    updated_at: datetime
    identity_mode: IdentityMode = IdentityMode.PSEUDONYM
    # Las instalaciones de este cliente quedan solo con el chat (sin Administración).
    config_locked: bool = False
    # Las instalaciones locales pueden ofrecer el CLI de Claude con la cuenta de la persona.
    allow_local_cli: bool = False
    # Proveedores permitidos y topes de IA (M3). Vacía = sin límites.
    ai_policy: AiPolicy = field(default_factory=AiPolicy)
    # Bases que puede consultar cada persona (M4). Vacía = lo que permita el ERP.
    access_policy: AccessPolicy = field(default_factory=AccessPolicy)


class InvalidClientCode(DomainError):
    code = "invalid_client_code"


class InvalidClientName(DomainError):
    code = "invalid_client_name"


class ClientCodeAlreadyExists(DomainError):
    code = "client_code_already_exists"


class ClientNotFound(DomainError):
    code = "client_not_found"


class ClientSuspended(DomainError):
    code = "client_suspended"


class ClientRepository(Protocol):
    async def add(self, client: Client) -> None:
        """Persiste. Levanta `ClientCodeAlreadyExists` si el código ya existe."""
        ...

    async def get_by_id(self, client_id: UUID) -> Client | None: ...

    async def get_by_code(self, code: str) -> Client | None: ...

    async def list_all(self) -> list[Client]: ...

    async def save(self, client: Client) -> None:
        """Persiste los campos mutables (nombre, NIT, estado)."""
        ...
