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
    # El proveedor devuelve el costo facturado del turno y no hace falta
    # cargar precios a mano. Los que no, lo calculan con la tabla de
    # precios del admin (`compute_cost_usd`): sin precio no hay costo.
    reports_cost: bool


PROVIDER_DESCRIPTORS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor(
        kind=ProviderKind.CLAUDE,
        display_name="Claude (Anthropic)",
        credential_kinds=(
            CredentialKind.API_KEY,
            CredentialKind.OAUTH_TOKEN,
            CredentialKind.LOCAL_SESSION,
        ),
        # API key y OAuth token usan el catálogo directo de Anthropic.
        supports_model_listing=True,
        implemented=True,
        # `ResultMessage.total_cost_usd` del SDK trae el costo real del turno.
        reports_cost=True,
    ),
    ProviderDescriptor(
        kind=ProviderKind.GEMINI,
        display_name="Gemini (Google)",
        credential_kinds=(CredentialKind.API_KEY,),
        supports_model_listing=True,
        implemented=True,
        reports_cost=False,
    ),
    ProviderDescriptor(
        kind=ProviderKind.OPENAI,
        display_name="OpenAI",
        credential_kinds=(CredentialKind.API_KEY,),
        # `GET /v1/models` lista los modelos visibles para la API key.
        supports_model_listing=True,
        implemented=True,
        reports_cost=False,
    ),
)


def get_descriptor(provider: str) -> ProviderDescriptor:
    for descriptor in PROVIDER_DESCRIPTORS:
        if descriptor.kind.value == provider:
            return descriptor
    raise LlmProviderNotFoundError(f"El proveedor de IA '{provider}' no existe.")
