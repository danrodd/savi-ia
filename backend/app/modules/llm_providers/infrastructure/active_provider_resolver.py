"""Impl del puerto `ActiveProviderResolver` del chat.

Cache en memoria del proceso **sin TTL**: la única forma de cambiar la
configuración es por este módulo, que invalida explícitamente en `save`
y `activate`. Expirar por tiempo solo agregaría lecturas a la BD.
"""
from __future__ import annotations

import asyncio

from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.chat.domain.interfaces import (
    ActiveProvider,
    ActiveProviderResolver,
    ModelPrice,
)
from app.modules.llm_providers.domain.entities import LlmProviderConfig, get_descriptor
from app.modules.llm_providers.domain.interfaces import LlmProviderRepository


class CachedActiveProviderResolver(ActiveProviderResolver):
    def __init__(self, repository: LlmProviderRepository) -> None:
        self._repository = repository
        self._cached: ActiveProvider | None = None
        # Sube en cada invalidación. Una lectura que empezó antes de un
        # `save` no puede dejar cacheada la configuración vieja.
        self._generation = 0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._generation += 1
        self._cached = None

    async def resolve(self) -> ActiveProvider:
        cached = self._cached
        if cached is not None:
            return cached
        async with self._lock:
            if self._cached is not None:
                return self._cached
            generation = self._generation
            provider = _to_active_provider(await self._repository.get_active())
            if generation == self._generation:
                self._cached = provider
            return provider


def _to_active_provider(config: LlmProviderConfig | None) -> ActiveProvider:
    if config is None:
        raise LlmProviderUnavailableError(
            "No hay un proveedor de IA activo. Un administrador tiene que "
            "configurarlo en la sección de administración."
        )
    if not get_descriptor(config.provider.value).implemented:
        raise LlmProviderUnavailableError(
            "El proveedor de IA activo no está disponible en esta versión de SAVI."
        )
    if not config.is_usable:
        raise LlmProviderUnavailableError(
            "La credencial del proveedor de IA no se puede leer o falta. Un "
            "administrador tiene que volver a ingresarla."
        )
    return ActiveProvider(
        kind=config.provider.value,
        chat_model=config.chat_model,
        title_model=config.title_model,
        credential_kind=config.credential_kind.value,
        credential=config.credential,
        pricing={
            model: ModelPrice(
                input=p.input,
                output=p.output,
                cache_read=p.cache_read,
                cache_write=p.cache_write,
            )
            for model, p in config.pricing.items()
        },
    )


_resolver: CachedActiveProviderResolver | None = None


def init_active_provider_resolver(
    repository: LlmProviderRepository,
) -> CachedActiveProviderResolver:
    global _resolver
    _resolver = CachedActiveProviderResolver(repository)
    return _resolver


def get_active_provider_resolver() -> CachedActiveProviderResolver:
    if _resolver is None:
        raise RuntimeError("init_active_provider_resolver() no se llamó en el lifespan.")
    return _resolver
