"""Administración de los proveedores de IA.

Reglas del dominio que viven acá y no en HTTP:

- **Credencial vacía = conservar la guardada**, igual que las bases del
  ERP. La credencial nunca vuelve al cliente para que la reenvíe.
- **Un solo activo**. Activar exige config usable (modelos y credencial
  legible, salvo `local_session`).
- **Invalidar la cache del resolver** tras `save` y `activate`: sin eso,
  el cambio no aplicaría al turno siguiente.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from app.modules.llm_providers.application.dtos import LlmProviderDTO, SaveLlmProviderDTO
from app.modules.llm_providers.domain.entities import (
    PROVIDER_DESCRIPTORS,
    LlmProviderConfig,
    ProviderDescriptor,
    get_descriptor,
)
from app.modules.llm_providers.domain.exceptions import LlmProviderNotImplementedError
from app.modules.llm_providers.domain.interfaces import (
    LlmProviderRepository,
    ProbeResult,
    ProviderProbe,
)
from app.modules.llm_providers.domain.value_objects import (
    CredentialKind,
    ModelInfo,
    ProviderKind,
)
from app.shared.exceptions import ValidationError


class ManageLlmProvidersUseCase:
    def __init__(
        self,
        repository: LlmProviderRepository,
        probes: Mapping[ProviderKind, ProviderProbe],
        on_change: Callable[[], None],
    ) -> None:
        self._repository = repository
        self._probes = probes
        self._on_change = on_change

    # ── Lectura ──────────────────────────────────────────────────────

    async def list(self) -> list[LlmProviderDTO]:
        configs = {c.provider: c for c in await self._repository.list_all()}
        return [LlmProviderDTO.build(d, configs.get(d.kind)) for d in PROVIDER_DESCRIPTORS]

    async def list_models(self, provider: str) -> list[ModelInfo]:
        descriptor = self._implemented(provider)
        if not descriptor.supports_model_listing:
            return []
        stored = await self._repository.get(descriptor.kind)
        if stored is None or not stored.has_credential:
            raise ValidationError(
                "Guardá una credencial válida antes de consultar los modelos."
            )
        return await self._probe(descriptor).list_models(stored)

    # ── Escritura ────────────────────────────────────────────────────

    async def save(self, provider: str, dto: SaveLlmProviderDTO) -> LlmProviderDTO:
        descriptor = self._implemented(provider)
        stored = await self._repository.get(descriptor.kind)
        candidate = self._candidate(descriptor, dto, stored)
        if stored is not None:
            candidate.id = stored.id
            candidate.is_active = stored.is_active
            # Una credencial nueva invalida la última prueba exitosa.
            if not dto.credential and candidate.credential_kind == stored.credential_kind:
                candidate.last_test_ok_at = stored.last_test_ok_at
        if candidate.is_active and not candidate.is_usable:
            # El mensaje tiene que nombrar lo que REALMENTE falta. Decía
            # siempre "sin credencial", y con `local_session` (que no lleva
            # credencial por definición) mandaba a buscar donde no estaba:
            # lo que faltaba eran los IDs de modelo.
            if not candidate.chat_model or not candidate.title_model:
                raise ValidationError(
                    "Este proveedor está activo: indicá el modelo de chat y el "
                    "de títulos antes de guardar."
                )
            raise ValidationError(
                "Este proveedor está activo: no se puede dejar sin credencial."
            )

        await self._repository.save(candidate)
        self._on_change()
        return LlmProviderDTO.build(descriptor, await self._repository.get(descriptor.kind))

    async def test(self, provider: str, dto: SaveLlmProviderDTO) -> ProbeResult:
        """El botón "probar" del formulario. No persiste la configuración.

        Si la prueba usó la credencial ya guardada y salió bien, sí marca
        `last_test_ok_at`: es la única forma de saber que la guardada sigue
        funcionando.
        """
        descriptor = self._implemented(provider)
        stored = await self._repository.get(descriptor.kind)
        candidate = self._candidate(descriptor, dto, stored)
        if (
            candidate.credential_kind != CredentialKind.LOCAL_SESSION
            and not candidate.has_credential
        ):
            return ProbeResult(ok=False, detail="Ingresá la credencial para probarla.")

        result = await self._probe(descriptor).test(candidate)
        if result.ok and stored is not None and candidate.credential == stored.credential:
            stored.last_test_ok_at = datetime.now(UTC)
            await self._repository.save(stored)
        return result

    async def activate(self, provider: str) -> LlmProviderDTO:
        descriptor = self._implemented(provider)
        stored = await self._repository.get(descriptor.kind)
        if stored is None:
            raise ValidationError("Configurá el proveedor antes de activarlo.")
        if not stored.is_usable:
            raise ValidationError(
                "No se puede activar: falta la credencial o no se puede leer."
            )
        await self._repository.activate(descriptor.kind)
        self._on_change()
        return LlmProviderDTO.build(descriptor, await self._repository.get(descriptor.kind))

    # ── Interno ──────────────────────────────────────────────────────

    def _implemented(self, provider: str) -> ProviderDescriptor:
        descriptor = get_descriptor(provider)
        if not descriptor.implemented:
            raise LlmProviderNotImplementedError(
                f"{descriptor.display_name} todavía no está disponible en esta versión."
            )
        return descriptor

    def _probe(self, descriptor: ProviderDescriptor) -> ProviderProbe:
        probe = self._probes.get(descriptor.kind)
        if probe is None:
            raise LlmProviderNotImplementedError(
                f"{descriptor.display_name} no tiene prueba de credencial."
            )
        return probe

    def _candidate(
        self,
        descriptor: ProviderDescriptor,
        dto: SaveLlmProviderDTO,
        stored: LlmProviderConfig | None,
    ) -> LlmProviderConfig:
        try:
            kind = CredentialKind(dto.credential_kind)
        except ValueError:
            kind = None
        if kind is None or kind not in descriptor.credential_kinds:
            allowed = ", ".join(k.value for k in descriptor.credential_kinds)
            raise ValidationError(
                f"Tipo de credencial no soportado por {descriptor.display_name}. "
                f"Opciones: {allowed}."
            )

        credential: str | None = None
        unreadable = False
        if kind != CredentialKind.LOCAL_SESSION:
            if dto.credential:
                credential = dto.credential
            elif stored is not None and stored.credential_kind == kind:
                # Vacía = conservar. Solo si es del mismo tipo: un token
                # OAuth guardado no sirve como API key.
                credential = stored.credential
                unreadable = stored.credentials_unreadable

        return LlmProviderConfig(
            provider=descriptor.kind,
            credential_kind=kind,
            credential=credential,
            credentials_unreadable=unreadable,
            chat_model=dto.chat_model,
            title_model=dto.title_model,
            document_model=(
                (dto.document_model or None)
                if dto.document_model is not None
                else (stored.document_model if stored else None)
            ),
            pricing=(
                dict(dto.pricing)
                if dto.pricing is not None
                else (dict(stored.pricing) if stored else {})
            ),
        )
