"""Suscripción de un cliente (M5-A): plan contratado y movimientos que registra el staff.

SAVI Cloud **no cobra**: los pagos se hacen por fuera y el staff los registra. Acá solo se
guarda qué plan tiene el cliente, hasta cuándo está pago y el historial de lo registrado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.shared.errors import DomainError

MAX_USD = Decimal("99999999")
MAX_NOTE = 500
MAX_USERS = 100000
_PLAN_NAME = re.compile(r"^\S.{0,79}$")


class InvalidSubscription(DomainError):
    code = "invalid_subscription"


class SubscriptionStatus(StrEnum):
    NONE = "none"  # sin plan o sin fecha de vigencia: no hay nada que vigilar
    ACTIVE = "active"
    EXPIRING = "expiring"  # vence dentro de la ventana de aviso
    EXPIRED = "expired"


def _money(value: object, *, allow_negative: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - cualquier valor ilegible es un monto inválido
        raise InvalidSubscription(f"Monto inválido: {value!r}.") from exc
    low = -MAX_USD if allow_negative else Decimal(0)
    if not amount.is_finite() or amount < low or amount > MAX_USD:
        raise InvalidSubscription("El monto está fuera de rango.")
    return amount.quantize(Decimal("0.01"))


def _fmt(amount: Decimal) -> str:
    return format(amount, "f")


@dataclass(frozen=True)
class Subscription:
    """Plan del cliente. Vacía = todavía no se le cargó ninguno."""

    plan_name: str | None = None
    monthly_fee_usd: Decimal | None = None
    # Cupo de personas del plan (informativo: se compara con los usuarios activos en la consola).
    max_users: int | None = None
    # Último día cubierto. `None` = sin vencimiento (no genera avisos).
    valid_until: date | None = None
    notes: str | None = None

    @property
    def is_empty(self) -> bool:
        return (
            self.plan_name is None
            and self.monthly_fee_usd is None
            and self.max_users is None
            and self.valid_until is None
            and self.notes is None
        )

    @classmethod
    def build(
        cls,
        *,
        plan_name: str | None,
        monthly_fee_usd: object | None,
        max_users: int | None,
        valid_until: date | None,
        notes: str | None,
    ) -> Subscription:
        name = plan_name.strip() if plan_name else None
        if name and not _PLAN_NAME.fullmatch(name):
            raise InvalidSubscription("El nombre del plan admite hasta 80 caracteres.")
        if max_users is not None and not 1 <= max_users <= MAX_USERS:
            raise InvalidSubscription("El cupo de personas debe ser mayor que cero.")
        note = notes.strip() if notes else None
        if note and len(note) > MAX_NOTE:
            raise InvalidSubscription(f"Las notas admiten hasta {MAX_NOTE} caracteres.")
        return cls(
            plan_name=name or None,
            monthly_fee_usd=_money(monthly_fee_usd) if monthly_fee_usd is not None else None,
            max_users=max_users,
            valid_until=valid_until,
            notes=note or None,
        )

    def extended_to(self, valid_until: date) -> Subscription:
        return Subscription(
            plan_name=self.plan_name,
            monthly_fee_usd=self.monthly_fee_usd,
            max_users=self.max_users,
            valid_until=valid_until,
            notes=self.notes,
        )

    def status(self, today: date, *, warn_days: int) -> SubscriptionStatus:
        if self.valid_until is None:
            return SubscriptionStatus.NONE
        remaining = (self.valid_until - today).days
        if remaining < 0:
            return SubscriptionStatus.EXPIRED
        if remaining <= warn_days:
            return SubscriptionStatus.EXPIRING
        return SubscriptionStatus.ACTIVE

    def to_json(self) -> dict[str, object]:
        return {
            "plan_name": self.plan_name,
            "monthly_fee_usd": _fmt(self.monthly_fee_usd)
            if self.monthly_fee_usd is not None
            else None,
            "max_users": self.max_users,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, raw: dict[str, object] | None) -> Subscription:
        if not raw:
            return cls()
        until = raw.get("valid_until")
        fee = raw.get("monthly_fee_usd")
        users = raw.get("max_users")
        name = raw.get("plan_name")
        notes = raw.get("notes")
        return cls(
            plan_name=name if isinstance(name, str) else None,
            monthly_fee_usd=Decimal(str(fee)) if fee is not None else None,
            max_users=users if isinstance(users, int) else None,
            valid_until=date.fromisoformat(until) if isinstance(until, str) else None,
            notes=notes if isinstance(notes, str) else None,
        )


class LedgerKind(StrEnum):
    PAYMENT = "payment"  # pago recibido (monto positivo)
    ADJUSTMENT = "adjustment"  # corrección o cortesía (puede ser negativa)


@dataclass(frozen=True)
class LedgerEntry:
    id: UUID
    client_id: UUID
    kind: LedgerKind
    amount_usd: Decimal
    note: str
    # Hasta cuándo deja cubierto el cliente este movimiento (opcional).
    extends_until: date | None
    created_by: str
    created_at: datetime

    @classmethod
    def build(
        cls,
        *,
        id: UUID,
        client_id: UUID,
        kind: LedgerKind,
        amount_usd: object,
        note: str,
        extends_until: date | None,
        created_by: str,
        created_at: datetime,
    ) -> LedgerEntry:
        text = note.strip()
        if not text:
            raise InvalidSubscription("El movimiento necesita una nota (referencia del pago).")
        if len(text) > MAX_NOTE:
            raise InvalidSubscription(f"La nota admite hasta {MAX_NOTE} caracteres.")
        amount = _money(amount_usd, allow_negative=kind is LedgerKind.ADJUSTMENT)
        if kind is LedgerKind.PAYMENT and amount == 0:
            raise InvalidSubscription("Un pago no puede ser de cero.")
        return cls(
            id=id,
            client_id=client_id,
            kind=kind,
            amount_usd=amount,
            note=text,
            extends_until=extends_until,
            created_by=created_by,
            created_at=created_at.astimezone(UTC),
        )


class LedgerRepository(Protocol):
    async def add(self, entry: LedgerEntry) -> None: ...

    async def list_by_client(self, client_id: UUID, *, limit: int) -> list[LedgerEntry]: ...
