"""Configuración persistida de un proveedor de IA.

La entidad viaja con la credencial **en claro**; el repositorio es la
frontera del cifrado. Nunca sale del backend: los DTOs de salida no
tienen el campo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.modules.llm_providers.domain.value_objects import (
    CredentialKind,
    ModelPricing,
    ProviderKind,
)


@dataclass(slots=True)
class LlmProviderConfig:
    provider: ProviderKind
    credential_kind: CredentialKind
    chat_model: str
    title_model: str
    # `None` con `local_session` o si no se cargó todavía.
    credential: str | None = None
    pricing: dict[str, ModelPricing] = field(default_factory=dict[str, ModelPricing])
    is_active: bool = False
    credentials_unreadable: bool = False
    last_test_ok_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def has_credential(self) -> bool:
        return bool(self.credential) and not self.credentials_unreadable

    @property
    def is_usable(self) -> bool:
        """Lista para atender un turno: modelos cargados y con qué autenticarse."""
        if not self.chat_model or not self.title_model:
            return False
        if self.credential_kind == CredentialKind.LOCAL_SESSION:
            return True
        return self.has_credential
