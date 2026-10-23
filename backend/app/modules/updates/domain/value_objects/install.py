"""Un intento de instalación y cómo terminó.

Todo puro. El vigilante (`infrastructure/watcher.py`) corre fuera de SAVI y
escribe un archivo con lo que vio; acá se lee ese archivo y se decide el
resultado final **contra la versión que está corriendo ahora**, que es la
prueba definitiva de si la instalación se aplicó.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from app.modules.updates.domain.exceptions.exceptions import (
    InvalidInstallResultError,
    InvalidVersionError,
)
from app.modules.updates.domain.value_objects.release import ReleaseVersion

# Tope del historial: alcanza para soporte y no crece sin límite.
HISTORY_LIMIT = 50


class WatcherStep(StrEnum):
    """Lo último que registró el vigilante."""

    STARTED = "started"
    # La persona canceló el permiso de administrador: el instalador no corrió.
    CANCELLED = "cancelled"
    # El instalador no arrancó o terminó con un código distinto de 0.
    FAILED = "failed"
    TIMEOUT = "timeout"
    # El instalador terminó con código 0 (o sin código legible).
    FINISHED = "finished"


class InstallOutcome(StrEnum):
    """Cómo terminó, ya contrastado con la versión que corre."""

    INSTALLED = "installed"
    # El instalador terminó bien pero SAVI sigue en la versión anterior.
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    # No quedó constancia de cómo terminó (equipo apagado, vigilante cortado).
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class InstallAttempt:
    attempt_id: str
    from_version: ReleaseVersion
    to_version: ReleaseVersion
    started_at: datetime


@dataclass(frozen=True)
class InstallResult:
    """Lo que escribió el vigilante en `last-install.json`."""

    attempt_id: str
    from_version: ReleaseVersion
    to_version: ReleaseVersion
    started_at: datetime
    step: WatcherStep
    exit_code: int | None = None
    finished_at: datetime | None = None
    relaunched: bool = False
    running_version: str | None = None

    @classmethod
    def from_mapping(cls, data: object) -> InstallResult:
        if not isinstance(data, Mapping):
            raise InvalidInstallResultError("El resultado de la instalación no es un objeto.")
        data = cast("Mapping[str, object]", data)
        try:
            return cls(
                attempt_id=_text(data, "attempt_id"),
                from_version=ReleaseVersion.parse(_text(data, "from_version")),
                to_version=ReleaseVersion.parse(_text(data, "to_version")),
                started_at=_instant(_text(data, "started_at"), "started_at"),
                step=WatcherStep(_text(data, "step")),
                exit_code=_optional_int(data, "exit_code"),
                finished_at=_optional_instant(data, "finished_at"),
                relaunched=data.get("relaunched") is True,
                running_version=_optional_text(data, "running_version"),
            )
        except (InvalidVersionError, ValueError) as exc:
            raise InvalidInstallResultError(f"Resultado de instalación inválido: {exc}") from exc


# Códigos de salida de Inno Setup ("Setup Exit Codes" de su documentación).
_EXIT_REASONS: dict[int, str] = {
    1: "no se pudo iniciar la instalación",
    2: "la instalación se canceló antes de empezar",
    3: "no se pudo preparar la instalación",
    4: "la instalación falló",
    5: "la instalación se canceló",
    6: "la instalación se interrumpió",
    7: "la instalación no pudo continuar",
    8: "la instalación necesita reiniciar el equipo",
}


def exit_reason(exit_code: int | None) -> str:
    if exit_code is None:
        return "no se pudo iniciar el instalador"
    return _EXIT_REASONS.get(exit_code, f"la instalación terminó con un error (código {exit_code})")


@dataclass(frozen=True)
class InstallRecord:
    """Una línea del historial: un intento ya resuelto."""

    attempt_id: str
    from_version: ReleaseVersion
    to_version: ReleaseVersion
    started_at: datetime
    finished_at: datetime
    outcome: InstallOutcome
    exit_code: int | None = None

    @property
    def message(self) -> str:
        """Texto para la persona, de usted."""
        target, origin = self.to_version, self.from_version
        match self.outcome:
            case InstallOutcome.INSTALLED:
                return f"SAVI se actualizó a {target}."
            case InstallOutcome.CANCELLED:
                return f"Se canceló el permiso de administrador: SAVI sigue en {origin}."
            case InstallOutcome.TIMEOUT:
                return (
                    f"La actualización a {target} tardó demasiado y se dejó de esperar. "
                    f"SAVI sigue en {origin}."
                )
            case InstallOutcome.INTERRUPTED:
                return f"La actualización a {target} no terminó. SAVI sigue en {origin}."
            case InstallOutcome.FAILED:
                return (
                    f"La actualización a {target} no se completó: "
                    f"{exit_reason(self.exit_code)}. SAVI sigue en {origin}."
                )
            case InstallOutcome.ROLLED_BACK:
                return f"La actualización a {target} no se completó. SAVI sigue en {origin}."

    def to_mapping(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "from_version": str(self.from_version),
            "to_version": str(self.to_version),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "outcome": self.outcome.value,
            "exit_code": self.exit_code,
        }

    @classmethod
    def from_mapping(cls, data: object) -> InstallRecord:
        if not isinstance(data, Mapping):
            raise InvalidInstallResultError("La línea del historial no es un objeto.")
        data = cast("Mapping[str, object]", data)
        try:
            return cls(
                attempt_id=_text(data, "attempt_id"),
                from_version=ReleaseVersion.parse(_text(data, "from_version")),
                to_version=ReleaseVersion.parse(_text(data, "to_version")),
                started_at=_instant(_text(data, "started_at"), "started_at"),
                finished_at=_instant(_text(data, "finished_at"), "finished_at"),
                outcome=InstallOutcome(_text(data, "outcome")),
                exit_code=_optional_int(data, "exit_code"),
            )
        except (InvalidVersionError, ValueError) as exc:
            raise InvalidInstallResultError(f"Línea del historial inválida: {exc}") from exc


def settle(result: InstallResult, running: ReleaseVersion, now: datetime) -> InstallRecord:
    """El resultado final de un intento, contrastado con la versión que corre.

    Que esté corriendo la versión de destino es la prueba definitiva de que se
    instaló, aunque el vigilante no haya llegado a escribir su último paso.
    """
    if result.step is WatcherStep.CANCELLED:
        outcome = InstallOutcome.CANCELLED
    elif running == result.to_version:
        outcome = InstallOutcome.INSTALLED
    elif result.step is WatcherStep.FAILED:
        outcome = InstallOutcome.FAILED
    elif result.step is WatcherStep.TIMEOUT:
        outcome = InstallOutcome.TIMEOUT
    elif result.step is WatcherStep.FINISHED:
        outcome = InstallOutcome.ROLLED_BACK
    else:
        outcome = InstallOutcome.INTERRUPTED
    return InstallRecord(
        attempt_id=result.attempt_id,
        from_version=result.from_version,
        to_version=result.to_version,
        started_at=result.started_at,
        finished_at=result.finished_at or now,
        outcome=outcome,
        exit_code=result.exit_code,
    )


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"falta {key}")
    return value.strip()


def _optional_text(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_int(data: Mapping[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} no es un entero")
    return value


def _instant(raw: str, key: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        raise ValueError(f"{key} no indica la zona horaria")
    return value


def _optional_instant(data: Mapping[str, object], key: str) -> datetime | None:
    value = _optional_text(data, key)
    return None if value is None else _instant(value, key)
