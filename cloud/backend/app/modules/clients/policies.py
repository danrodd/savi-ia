"""Políticas que Cloud fija por cliente: IA (proveedores y topes) y acceso a bases.

Valores inmutables y validados. Cloud decide; la instancia mide y aplica.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from app.shared.errors import DomainError

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


MAX_GROUPS = 50
MAX_GROUP_NAME = 80
_GROUP_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class AccessGroup:
    """Grupo con nombre: personas que comparten las mismas bases (ej. "Soporte zona norte")."""

    id: str
    name: str
    members: tuple[str, ...]
    databases: tuple[str, ...]


def _group(raw: Mapping[str, object]) -> AccessGroup:
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > MAX_GROUP_NAME:
        raise InvalidAccessPolicy(
            f"El grupo necesita un nombre de hasta {MAX_GROUP_NAME} caracteres."
        )
    given = str(raw.get("id") or "").strip().lower()
    if given and not _GROUP_ID.fullmatch(given):
        raise InvalidAccessPolicy("Identificador de grupo inválido.")
    members_raw = raw.get("members")
    databases_raw = raw.get("databases")
    members = tuple(
        dict.fromkeys(str(m).strip().lower() for m in members_raw)  # pyright: ignore[reportUnknownArgumentType,reportUnknownVariableType]
        if isinstance(members_raw, (list, tuple))
        else ()
    )
    if len(members) > MAX_USER_OVERRIDES:
        raise InvalidAccessPolicy(f"Máximo {MAX_USER_OVERRIDES} personas por grupo.")
    for ref in members:
        if not _USER_REF.fullmatch(ref):
            raise InvalidAccessPolicy("Identificador de persona inválido.")
    refs: list[str] = (
        [str(d) for d in cast("list[Any]", databases_raw)]
        if isinstance(databases_raw, (list, tuple))
        else []
    )
    databases = _databases(refs)
    return AccessGroup(id=given or uuid4().hex, name=name, members=members, databases=databases)


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
    # Grupos con nombre. Se compilan a reglas por persona al bajar a las instalaciones.
    groups: tuple[AccessGroup, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.default_databases is None and not self.user_databases and not self.groups

    def compiled_user_databases(self) -> dict[str, tuple[str, ...]]:
        """Regla efectiva por persona: unión de las bases de sus grupos, y la regla propia
        (si la tiene) manda sobre los grupos."""
        merged: dict[str, set[str]] = {}
        for group in self.groups:
            for member in group.members:
                merged.setdefault(member, set()).update(group.databases)
        compiled = {member: tuple(sorted(refs)) for member, refs in merged.items()}
        compiled.update(self.user_databases)
        return compiled

    def to_wire(self) -> dict[str, object]:
        """Lo que baja a la instancia: el contrato no conoce los grupos."""
        return {
            "default_databases": list(self.default_databases)
            if self.default_databases is not None
            else None,
            "user_databases": {k: list(v) for k, v in self.compiled_user_databases().items()},
        }

    @classmethod
    def build(
        cls,
        *,
        default_databases: Sequence[str] | None,
        user_databases: Mapping[str, Sequence[str]],
        groups: Sequence[Mapping[str, object]] = (),
    ) -> AccessPolicy:
        if len(user_databases) > MAX_USER_OVERRIDES:
            raise InvalidAccessPolicy(f"Máximo {MAX_USER_OVERRIDES} personas con regla propia.")
        for ref in user_databases:
            if not _USER_REF.fullmatch(ref):
                raise InvalidAccessPolicy("Identificador de persona inválido.")
        if len(groups) > MAX_GROUPS:
            raise InvalidAccessPolicy(f"Máximo {MAX_GROUPS} grupos por cliente.")
        built = tuple(_group(g) for g in groups)
        names = [g.name.casefold() for g in built]
        if len(set(names)) != len(names):
            raise InvalidAccessPolicy("Dos grupos no pueden tener el mismo nombre.")
        ids = [g.id for g in built]
        if len(set(ids)) != len(ids):
            raise InvalidAccessPolicy("Identificador de grupo repetido.")
        policy = cls(
            default_databases=_databases(default_databases)
            if default_databases is not None
            else None,
            user_databases={k: _databases(v) for k, v in user_databases.items()},
            groups=built,
        )
        # El contrato admite hasta 500 personas con regla: se valida ya compilado.
        if len(policy.compiled_user_databases()) > MAX_USER_OVERRIDES:
            raise InvalidAccessPolicy(
                f"Las reglas y grupos alcanzan a más de {MAX_USER_OVERRIDES} personas."
            )
        return policy

    def to_json(self) -> dict[str, object]:
        return {
            "default_databases": list(self.default_databases)
            if self.default_databases is not None
            else None,
            "user_databases": {k: list(v) for k, v in self.user_databases.items()},
            "groups": [
                {
                    "id": g.id,
                    "name": g.name,
                    "members": list(g.members),
                    "databases": list(g.databases),
                }
                for g in self.groups
            ],
        }

    @classmethod
    def from_json(cls, raw: dict[str, object] | None) -> AccessPolicy:
        if not raw:
            return cls()
        default = raw.get("default_databases")
        users = raw.get("user_databases")
        groups = raw.get("groups")
        return cls.build(
            groups=[
                cast("dict[str, object]", g)
                for g in cast("list[Any]", groups)
                if isinstance(g, dict)
            ]
            if isinstance(groups, list)
            else [],
            default_databases=list(default) if isinstance(default, list) else None,  # pyright: ignore[reportUnknownArgumentType]
            user_databases={str(k): list(v) for k, v in users.items()}  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
            if isinstance(users, dict)
            else {},
        )
