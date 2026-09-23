"""Arma el lector de PDF del proveedor de IA activo.

Usa el mismo resolver que el chat (`ActiveProviderResolver`), así que
cambiar el proveedor o su credencial en administración aplica al próximo
documento sin reiniciar.
"""

from app.modules.chat.domain.exceptions import LlmProviderUnavailableError
from app.modules.chat.domain.interfaces import ActiveProvider, ActiveProviderResolver
from app.modules.company_knowledge.domain.interfaces import (
    AiReaderAvailability,
    AiReaderProvider,
    PdfPageReader,
)
from app.modules.company_knowledge.infrastructure.ai_reading.claude_reader import (
    ClaudePdfReader,
)
from app.modules.company_knowledge.infrastructure.ai_reading.gemini_reader import (
    GeminiPdfReader,
)
from app.modules.company_knowledge.infrastructure.ai_reading.openai_reader import (
    OpenAiPdfReader,
)

_SUPPORTED = ("claude", "gemini", "openai")


class ActiveProviderAiReaderProvider(AiReaderProvider):
    def __init__(self, resolver: ActiveProviderResolver, *, git_bash_path: str = "") -> None:
        self._resolver = resolver
        self._git_bash_path = git_bash_path

    async def availability(self) -> AiReaderAvailability:
        try:
            provider = await self._resolver.resolve()
        except LlmProviderUnavailableError as exc:
            return AiReaderAvailability(available=False, reason=exc.reason)
        if provider.kind not in _SUPPORTED:
            return AiReaderAvailability(
                available=False,
                provider=provider.kind,
                reason="El proveedor de IA activo no puede leer documentos.",
            )
        model = _model(provider)
        price = provider.pricing.get(model)
        return AiReaderAvailability(
            available=True,
            provider=provider.kind,
            model=model,
            credential_kind=provider.credential_kind,
            input_price=price.input if price else None,
            output_price=price.output if price else None,
        )

    async def build_reader(self) -> PdfPageReader | None:
        try:
            provider = await self._resolver.resolve()
        except LlmProviderUnavailableError:
            return None
        model = _model(provider)
        if provider.kind == "claude":
            return ClaudePdfReader(
                model=model,
                credential_kind=provider.credential_kind,
                credential=provider.credential,
                git_bash_path=self._git_bash_path,
            )
        if provider.kind == "openai":
            return OpenAiPdfReader(
                model=model, api_key=provider.credential, price=provider.pricing.get(model)
            )
        if provider.kind == "gemini":
            return GeminiPdfReader(
                model=model, api_key=provider.credential, price=provider.pricing.get(model)
            )
        return None


def _model(provider: ActiveProvider) -> str:
    return provider.document_model or provider.chat_model
