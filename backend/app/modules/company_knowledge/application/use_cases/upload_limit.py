"""Cupo de subidas por usuario y por hora, configurable desde la pantalla.

Lo comparten subir, reemplazar, agregar un sitio y pedir "Leer ahora":
todas encolan procesamiento. El servidor fija el valor por defecto y un
techo (`.env`); un administrador elige un valor dentro de ese techo sin
tocar el servidor, o vuelve al por defecto.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from app.modules.company_knowledge.domain.entities import KnowledgeSettings
from app.modules.company_knowledge.domain.exceptions import CompanyDocumentInvalidError
from app.modules.company_knowledge.domain.interfaces import KnowledgeSettingsRepository


@dataclass(frozen=True, slots=True)
class UploadLimit:
    configured: int | None  # `None`: se usa el por defecto
    default: int
    maximum: int
    effective: int
    updated_by_login: str | None
    updated_at: datetime | None


class UploadLimitUseCase:
    def __init__(
        self, settings: KnowledgeSettingsRepository, *, default: int, maximum: int
    ) -> None:
        self._settings = settings
        self._default = default
        self._maximum = maximum

    async def get(self) -> UploadLimit:
        current = await self._settings.get()
        return self._build(current)

    async def update(self, value: int | None, *, updated_by_login: str) -> UploadLimit:
        if value is not None and not 1 <= value <= self._maximum:
            raise CompanyDocumentInvalidError(
                f"El cupo debe estar entre 1 y {self._maximum} por hora."
            )
        current = await self._settings.get()
        saved = await self._settings.save(
            replace(current, upload_limit_per_hour=value, updated_by_login=updated_by_login)
        )
        return self._build(saved)

    def _build(self, settings: KnowledgeSettings) -> UploadLimit:
        configured = settings.upload_limit_per_hour
        effective = self._default if configured is None else min(configured, self._maximum)
        return UploadLimit(
            configured=configured,
            default=self._default,
            maximum=self._maximum,
            effective=max(1, effective),
            updated_by_login=settings.updated_by_login,
            updated_at=settings.updated_at,
        )
