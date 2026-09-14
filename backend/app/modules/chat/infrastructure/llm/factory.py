"""Construye el runner y el generador de títulos del proveedor activo.

Único lugar del chat que sabe qué adaptador corresponde a cada
proveedor. Agregar uno es sumar una rama acá.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from app.infrastructure.config import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import ChatEvent, ErrorEvent
from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.chat.domain.interfaces import (
    ActiveProvider,
    ActiveProviderResolver,
    LLMRunner,
    TitleGenerator,
)
from app.modules.chat.infrastructure.llm.claude.runner import ClaudeAgentRunner
from app.modules.chat.infrastructure.llm.claude.title_generator import ClaudeTitleGenerator

log = logging.getLogger(__name__)


class LLMRunnerFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build(self, provider: ActiveProvider) -> LLMRunner:
        if provider.kind == "claude":
            return ClaudeAgentRunner(self._settings, provider)
        raise LlmProviderUnavailableError(
            "El proveedor de IA activo no está disponible en esta versión de SAVI."
        )


class TitleGeneratorFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build(self, provider: ActiveProvider) -> TitleGenerator:
        if provider.kind == "claude":
            return ClaudeTitleGenerator(self._settings, provider)
        raise LlmProviderUnavailableError(
            "El proveedor de IA activo no está disponible en esta versión de SAVI."
        )


class ResolvingLLMRunner(LLMRunner):
    """Resuelve el proveedor al empezar el stream, no al armar el caso de uso.

    La ruta ya resolvió antes de abrir el SSE para devolver un 409 limpio;
    esta segunda resolución sale de la cache. Si justo en el medio un
    administrador desactivó el proveedor, el turno termina con un evento
    de error en vez de romper el stream.
    """

    def __init__(self, resolver: ActiveProviderResolver, factory: LLMRunnerFactory) -> None:
        self._resolver = resolver
        self._factory = factory

    async def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        try:
            runner = self._factory.build(await self._resolver.resolve())
        except LlmProviderUnavailableError as e:
            yield ErrorEvent(message=e.reason)
            return
        async for event in runner.stream_turn(
            prompt,
            conversation_id=conversation_id,
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
        ):
            yield event


class ResolvingTitleGenerator(TitleGenerator):
    """Resuelve el proveedor al momento de generar el título.

    El título se genera en segundo plano y puede correr después del
    turno: si el administrador cambió de proveedor en el medio, usa el
    nuevo.
    """

    def __init__(
        self, resolver: ActiveProviderResolver, factory: TitleGeneratorFactory
    ) -> None:
        self._resolver = resolver
        self._factory = factory

    async def generate(self, user_msg: str, assistant_msg: str = "") -> str | None:
        try:
            generator = self._factory.build(await self._resolver.resolve())
        except LlmProviderUnavailableError as e:
            log.warning("title_generation_skipped reason=%s", e.reason)
            return None
        return await generator.generate(user_msg, assistant_msg)
