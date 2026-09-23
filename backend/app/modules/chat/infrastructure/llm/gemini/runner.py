from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import Protocol, cast
from uuid import UUID, uuid4

from google import genai
from google.genai import types

from app.infrastructure.config import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolResult,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import ActiveProvider, LLMRunner
from app.modules.chat.infrastructure.llm.errors import user_facing_error
from app.modules.chat.infrastructure.llm.gemini.mapping import (
    add_usage,
    function_response_part,
)
from app.modules.chat.infrastructure.llm.pricing import compute_cost_usd
from app.modules.chat.infrastructure.llm.system_prompt import build_system_prompt, today_in
from app.modules.chat.infrastructure.llm.tools.registry import build_savi_tools
from app.modules.chat.infrastructure.llm.truncation import ResponseTruncator
from app.modules.company_knowledge.domain.services import TurnDocumentContext
from app.modules.conversations.domain.value_objects import TokenUsage

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = (429, 503)
_AUTH_STATUS = (401, 403)
_SECURITY_REASONS = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
_SECURITY_MESSAGE = "No pude generar una respuesta para esa consulta."
_CREDENTIAL_REMEDY = (
    "La API key de Gemini no es válida o no tiene permisos. Revisá la configuración "
    "del proveedor y volvé a intentar."
)


class _Models(Protocol):
    def generate_content_stream(
        self,
        *,
        model: str,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
    ) -> Awaitable[AsyncIterator[types.GenerateContentResponse]]: ...


class _AsyncClient(Protocol):
    models: _Models


class _Client(Protocol):
    aio: _AsyncClient


def _status(error: Exception) -> int | None:
    value = getattr(error, "code", None)
    return value if isinstance(value, int) else None


def _finish_reason(response: types.GenerateContentResponse) -> str | None:
    candidates = response.candidates or []
    if not candidates:
        return None
    reason = candidates[0].finish_reason
    return reason.value if reason is not None else None


def _is_thinking_error(error: Exception) -> bool:
    text = str(error).lower()
    return "thinking" in text and ("support" in text or "invalid" in text)


class GeminiRunner(LLMRunner):
    def __init__(
        self,
        settings: Settings,
        provider: ActiveProvider,
        *,
        client: _Client | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._client = client

    def _config(self, tools: list[ToolSpec], *, thinking: bool) -> types.GenerateContentConfig:
        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.parameters,
            )
            for tool in tools
        ]
        return types.GenerateContentConfig(
            system_instruction=build_system_prompt(today_in(self._settings.reporting_timezone)),
            tools=[types.Tool(function_declarations=declarations)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(include_thoughts=True) if thinking else None,
        )

    async def _stream(
        self,
        client: _Client,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
        model: str,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        stream = client.aio.models.generate_content_stream(
            model=model, contents=contents, config=config
        )
        if inspect.isawaitable(stream):
            stream = await stream
        async for chunk in stream:
            yield chunk

    async def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
        document_context: TurnDocumentContext | None = None,
    ) -> AsyncIterator[ChatEvent]:
        client = self._client or genai.Client(api_key=self._provider.credential)
        tools = build_savi_tools(
            conversation_id=conversation_id,
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
            document_context=document_context,
        )
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        usage = TokenUsage()
        truncator = ResponseTruncator(self._settings.max_response_chars)
        thinking = True
        first_token = False
        thinking_retry = False
        models = [self._provider.chat_model]
        models.extend(
            model
            for model in self._settings.gemini_fallback_models_list
            if model != self._provider.chat_model
        )
        model_index = 0
        selected_model = models[model_index]
        retry_attempt = 0
        iteration = 0

        while iteration < self._settings.max_agent_turns:
            iteration += 1
            model_parts: list[types.Part] = []
            calls: list[types.FunctionCall] = []
            last_reason: str | None = None
            iteration_usage: TokenUsage | None = None
            try:
                stream = self._stream(
                    cast(_Client, client),
                    contents,
                    self._config(tools, thinking=thinking),
                    selected_model,
                )
                async for chunk in stream:
                    if chunk.usage_metadata is not None:
                        # Gemini may repeat cumulative metadata in every chunk.
                        # Keep only the last snapshot for this request, then add
                        # the request total once after the stream finishes.
                        iteration_usage = add_usage(TokenUsage(), chunk.usage_metadata)
                    for candidate in chunk.candidates or []:
                        last_reason = _finish_reason(chunk)
                        if candidate.content is None:
                            continue
                        for part in candidate.content.parts or []:
                            model_parts.append(part)
                            if part.thought and part.text:
                                yield ThinkingDeltaEvent(text=part.text)
                            elif part.text:
                                first_token = True
                                for event in truncator.feed(part.text):
                                    yield event
                            if part.function_call is not None:
                                calls.append(part.function_call)
            except Exception as error:  # noqa: BLE001
                code = _status(error)
                if code in _AUTH_STATUS:
                    yield ErrorEvent(
                        message=user_facing_error(
                            "La API key de Gemini no es válida o no tiene permisos.",
                            credential_remedy=_CREDENTIAL_REMEDY,
                        )
                    )
                    return
                if code in _RETRYABLE_STATUS and not first_token:
                    retry_attempt += 1
                    if retry_attempt <= self._settings.gemini_retry_attempts:
                        log.warning(
                            "gemini_retry model=%s status=%s attempt=%s",
                            selected_model,
                            code,
                            retry_attempt,
                        )
                        await asyncio.sleep(
                            self._settings.gemini_retry_base_delay_s * (2 ** (retry_attempt - 1))
                        )
                        continue
                    model_index += 1
                    if model_index < len(models):
                        selected_model = models[model_index]
                        retry_attempt = 0
                        log.warning(
                            "gemini_retry model=%s status=%s attempt=%s",
                            selected_model,
                            code,
                            retry_attempt,
                        )
                        continue
                if code in _RETRYABLE_STATUS and not first_token:
                    log.warning(
                        "gemini_retry model=%s status=%s attempt=%s",
                        selected_model,
                        code,
                        retry_attempt,
                    )
                    yield ErrorEvent(message="No pude generar una respuesta para esa consulta.")
                    return
                if _is_thinking_error(error) and not first_token and not thinking_retry:
                    thinking_retry = True
                    thinking = False
                    continue
                log.error(
                    "gemini_turn_failed model=%s status=%s attempt=%s",
                    selected_model,
                    code,
                    retry_attempt,
                )
                yield ErrorEvent(
                    message=(
                        str(error)
                        if first_token
                        else "No pude generar una respuesta para esa consulta."
                    )
                )
                return

            if last_reason in _SECURITY_REASONS:
                yield ErrorEvent(message=_SECURITY_MESSAGE)
                return
            if iteration_usage is not None:
                usage = TokenUsage(
                    input_tokens=usage.input_tokens + iteration_usage.input_tokens,
                    output_tokens=usage.output_tokens + iteration_usage.output_tokens,
                    cache_read_input_tokens=(
                        usage.cache_read_input_tokens + iteration_usage.cache_read_input_tokens
                    ),
                    cache_creation_input_tokens=(
                        usage.cache_creation_input_tokens
                        + iteration_usage.cache_creation_input_tokens
                    ),
                )
            if not calls:
                finish = "truncated" if last_reason == "MAX_TOKENS" else "complete"
                yield DoneEvent(
                    usage=usage.to_dict(),
                    cost_usd=compute_cost_usd(usage, self._provider.pricing.get(selected_model)),
                    finish_reason=finish,
                    provider=self._provider.kind,
                    model=selected_model,
                )
                return

            contents.append(types.Content(role="model", parts=model_parts))
            responses: list[types.Part] = []
            for call in calls:
                name = call.name or ""
                call_id = call.id or str(uuid4())
                args = dict(call.args or {})
                yield ToolUseEvent(id=call_id, name=name, input=args)
                spec = next((tool for tool in tools if tool.name == name), None)
                if spec is None:
                    result_text = f"No existe la herramienta '{name}'."
                    is_error = True
                else:
                    try:
                        result = await spec.handler(args)
                        result_text, is_error = result.text, result.is_error
                    except Exception as error:  # noqa: BLE001
                        log.exception("gemini_tool_failed name=%s", name)
                        result_text, is_error = str(error), True
                yield ToolResultEvent(tool_use_id=call_id, is_error=is_error)
                responses.append(function_response_part(name, ToolResult(result_text, is_error)))
            contents.append(types.Content(role="user", parts=responses))

        yield TextDeltaEvent(text="\n\nRespuesta truncada por límite de iteraciones.")
        yield DoneEvent(
            usage=usage.to_dict(),
            cost_usd=compute_cost_usd(usage, self._provider.pricing.get(selected_model)),
            finish_reason="truncated",
            provider=self._provider.kind,
            model=selected_model,
        )
