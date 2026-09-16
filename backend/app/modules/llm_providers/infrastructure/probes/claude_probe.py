"""Prueba de credencial de Claude y listado de modelos de Anthropic."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Protocol, cast

from anthropic import AsyncAnthropic
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from app.infrastructure.claude_cli import ISOLATED_CLI_OPTIONS, resolve_cli_path
from app.infrastructure.claude_env import build_claude_env
from app.infrastructure.config import Settings
from app.modules.llm_providers.domain.entities import LlmProviderConfig
from app.modules.llm_providers.domain.interfaces import ProbeResult, ProviderProbe
from app.modules.llm_providers.domain.value_objects import (
    CredentialKind,
    ModelInfo,
)

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 90
_CREDENTIAL_HINTS = ("401", "invalid api key", "authentication", "oauth", "unauthorized")


class _ModelPage(Protocol):
    @property
    def data(self) -> Sequence[object]: ...


class _Models(Protocol):
    async def list(self, *, limit: int) -> _ModelPage: ...


class _AnthropicClient(Protocol):
    @property
    def models(self) -> _Models: ...


ClientFactory = Callable[[CredentialKind, str], _AnthropicClient]


class ClaudeProbe(ProviderProbe):
    def __init__(
        self, settings: Settings, *, client_factory: ClientFactory | None = None
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory

    async def test(self, config: LlmProviderConfig) -> ProbeResult:
        if not config.title_model:
            if config.credential_kind == CredentialKind.LOCAL_SESSION:
                return ProbeResult(
                    ok=False,
                    detail=(
                        "Ingresá un ID de modelo: el login local de Claude no expone "
                        "un catálogo de modelos."
                    ),
                )
            try:
                models = await self._fetch_models(config)
            except Exception as e:  # noqa: BLE001
                return ProbeResult(ok=False, detail=_detail_for(str(e)))
            return ProbeResult(
                ok=True,
                detail="La credencial de Claude es válida. Elegí un modelo de la lista.",
                models=tuple(models),
            )

        options = ClaudeAgentOptions(
            model=config.title_model,
            system_prompt="Respondé únicamente con la palabra: ok",
            allowed_tools=[],
            permission_mode="bypassPermissions",
            max_turns=1,
            cli_path=resolve_cli_path(),
            env=build_claude_env(
                credential_kind=config.credential_kind.value,
                credential=config.credential,
                git_bash_path=self._settings.claude_code_git_bash_path,
            ),
            # Sin la configuración del equipo: ver `ISOLATED_CLI_OPTIONS`.
            **ISOLATED_CLI_OPTIONS,
        )
        text: list[str] = []
        result: ResultMessage | None = None
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
                async for msg in query(prompt="ping", options=options):
                    if isinstance(msg, AssistantMessage):
                        text.extend(b.text for b in msg.content if isinstance(b, TextBlock))
                    elif isinstance(msg, ResultMessage):
                        result = msg
        except TimeoutError:
            return ProbeResult(
                ok=False,
                detail="Claude no respondió a tiempo. Revisá la conexión a internet.",
            )
        except Exception as e:  # noqa: BLE001
            # `result` ya llegó: el error es ruido del cierre del subproceso.
            if result is None:
                logger.warning("claude_probe_failed error=%s", e)
                return ProbeResult(ok=False, detail=_detail_for(str(e)))

        if result is None or result.is_error:
            return ProbeResult(ok=False, detail=_detail_for(" ".join(text)))
        models = await self.list_models(config)
        return ProbeResult(
            ok=True,
            detail=f"Claude respondió con el modelo {config.title_model}.",
            models=tuple(models),
        )

    async def list_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        if config.credential_kind == CredentialKind.LOCAL_SESSION or not config.credential:
            return []
        try:
            return await self._fetch_models(config)
        except Exception:  # noqa: BLE001
            logger.exception("claude_model_listing_failed")
            return []

    async def _fetch_models(self, config: LlmProviderConfig) -> list[ModelInfo]:
        client = self._client(config.credential_kind, config.credential or "")
        page = await client.models.list(limit=100)
        return [
            ModelInfo(
                id=model_id,
                display_name=str(getattr(model, "display_name", model_id) or model_id),
            )
            for model in page.data
            if (model_id := str(getattr(model, "id", "") or ""))
        ]

    def _client(self, kind: CredentialKind, credential: str) -> _AnthropicClient:
        if self._client_factory is not None:
            return self._client_factory(kind, credential)
        if kind == CredentialKind.OAUTH_TOKEN:
            return cast(_AnthropicClient, AsyncAnthropic(auth_token=credential))
        return cast(_AnthropicClient, AsyncAnthropic(api_key=credential))


def _detail_for(message: str) -> str:
    lowered = message.lower()
    if any(hint in lowered for hint in _CREDENTIAL_HINTS):
        return "La credencial de Claude no es válida o venció."
    if "model" in lowered:
        return "Claude rechazó el modelo configurado. Revisá el ID del modelo de títulos."
    detail = message.strip()[:300]
    return f"No se pudo usar Claude: {detail}" if detail else "No se pudo usar Claude."
