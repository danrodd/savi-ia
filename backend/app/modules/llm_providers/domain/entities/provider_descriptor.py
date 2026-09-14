"""Catálogo estático de proveedores: qué pide cada uno y qué sabe hacer.

No persiste. La UI lo usa para saber qué campos mostrar y la factory del
chat para saber qué adaptador construir. Agregar un proveedor es agregar
un descriptor acá y su adaptador; la API no cambia.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.llm_providers.domain.exceptions import LlmProviderNotFoundError
from app.modules.llm_providers.domain.value_objects import CredentialKind, ProviderKind


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    kind: ProviderKind
    display_name: str
    credential_kinds: tuple[CredentialKind, ...]
    supports_model_listing: bool
    implemented: bool


PROVIDER_DESCRIPTORS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor(
        kind=ProviderKind.CLAUDE,
        display_name="Claude (Anthropic)",
        credential_kinds=(
            CredentialKind.API_KEY,
            CredentialKind.OAUTH_TOKEN,
            CredentialKind.LOCAL_SESSION,
        ),
        # El SDK no expone un listado de modelos: se ingresan a mano.
        supports_model_listing=False,
        implemented=True,
    ),
    ProviderDescriptor(
        kind=ProviderKind.GEMINI,
        display_name="Gemini (Google)",
        credential_kinds=(CredentialKind.API_KEY,),
        supports_model_listing=True,
        implemented=False,
    ),
)


def get_descriptor(provider: str) -> ProviderDescriptor:
    for descriptor in PROVIDER_DESCRIPTORS:
        if descriptor.kind.value == provider:
            return descriptor
    raise LlmProviderNotFoundError(f"El proveedor de IA '{provider}' no existe.")
