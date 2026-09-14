"""Adaptador de OpenAI sobre la Responses API.

Por qué Responses y no Chat Completions: es la API vigente para streaming,
function calling y modelos de razonamiento. Igual que con Gemini, el loop
de tools es manual — el adaptador las traduce desde el registro neutral y
controla los eventos y el límite de iteraciones.

Regla que no se puede perder: cuando el modelo pide una tool, hay que
reenviar **todos** los output items de esa respuesta (incluidos los de
razonamiento) en el siguiente request. Enviar solo el texto visible hace
que la segunda vuelta falle o pierda contexto.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import Any, Protocol, cast
from uuid import UUID

from openai import AsyncOpenAI

from app.infrastructure.config import Settings
from app.modules.auth.domain.value_objects.module_code import ModuleCode
from app.modules.chat.domain.entities import (
    ChatEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolResult,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
)
from app.modules.chat.domain.interfaces import ActiveProvider, LLMRunner
from app.modules.chat.infrastructure.llm.errors import user_facing_error
from app.modules.chat.infrastructure.llm.openai.mapping import (
    add_usage,
    function_call_output,
    tool_definitions,
)
from app.modules.chat.infrastructure.llm.pricing import compute_cost_usd
from app.modules.chat.infrastructure.llm.system_prompt import SYSTEM_PROMPT
from app.modules.chat.infrastructure.llm.tools.registry import build_savi_tools
from app.modules.chat.infrastructure.llm.truncation import ResponseTruncator
from app.modules.conversations.domain.value_objects import TokenUsage

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = (429, 500, 502, 503, 504)
_AUTH_STATUS = (401, 403)
_SECURITY_MESSAGE = "No pude generar una respuesta para esa consulta."
_CREDENTIAL_REMEDY = (
    "La API key de OpenAI no es válida o no tiene permisos. Revisá la configuración "
    "del proveedor y volvé a intentar."
)
_TRUNCATED_REASONS = {"max_output_tokens", "max_tokens"}


class _Responses(Protocol):
    def create(self, **kwargs: Any) -> Awaitable[AsyncIterator[Any]]: ...


class _AsyncClient(Protocol):
    responses: _Responses


def _status(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    return value if isinstance(value, int) else None


def _quota_exhausted(error: Exception) -> bool:
    """`429` por saldo agotado no se reintenta: no es un límite temporal.

    Duplicado a propósito del helper del probe: `llm_providers` importa
    `chat`, así que compartirlo invertiría la dependencia en ciclo.
    """
    body: Any = getattr(error, "body", None)
    if isinstance(body, dict):
        data = cast("dict[str, Any]", body)
        code = data.get("code")
        etype = data.get("type")
        if code in ("credit_balance_exhausted", "insufficient_quota"):
            return True
        if etype == "insufficient_quota":
            return True
    return getattr(error, "code", None) in (
        "credit_balance_exhausted",
        "insufficient_quota",
    )


def _failure_code(event: Any) -> int | None:
    """Código de un evento `response.failed`/`error`.

    La SDK expone el detalle en `event.response.error`, no en un atributo
    `message`; buscamos ambas rutas para no perderlo.
    """
    response = getattr(event, "response", None)
    error = getattr(response, "error", None) if response is not None else None
    if error is None:
        error = getattr(event, "error", None)
    code = getattr(error, "code", None)
    return code if isinstance(code, int) else None


class OpenAIRunner(LLMRunner):
    def __init__(
        self,
        settings: Settings,
        provider: ActiveProvider,
        *,
        client: _AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._client = client

    async def _stream(
        self,
        client: _AsyncClient,
        model: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[Any]:
        result = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=input_items,
            tools=tools,
            stream=True,
            store=False,
        )
        stream = await result if inspect.isawaitable(result) else result
        async for event in stream:
            yield event

    async def stream_turn(
        self,
        prompt: str,
        *,
        conversation_id: UUID | None = None,
        allowed_modules: frozenset[ModuleCode] | None = None,
        erp_database_id: UUID | None = None,
    ) -> AsyncIterator[ChatEvent]:
        client = cast(
            _AsyncClient, self._client or AsyncOpenAI(api_key=self._provider.credential)
        )
        tool_specs = build_savi_tools(
            conversation_id=conversation_id,
            allowed_modules=allowed_modules,
            erp_database_id=erp_database_id,
        )
        tools = tool_definitions(tool_specs)
        # Mezcla deliberada de dicts neutros y objetos de la SDK: la API
        # acepta ambos y reenviar el objeto original preserva los items de
        # razonamiento que solo ella sabe serializar.
        input_items: list[Any] = [{"role": "user", "content": prompt}]
        usage = TokenUsage()
        truncator = ResponseTruncator(self._settings.max_response_chars)
        first_token = False
        models = [self._provider.chat_model]
        models.extend(
            model
            for model in self._settings.openai_fallback_models_list
            if model != self._provider.chat_model
        )
        model_index = 0
        selected_model = models[model_index]
        retry_attempt = 0
        iteration = 0

        while iteration < self._settings.max_agent_turns:
            iteration += 1
            output_items: list[Any] = []
            function_calls: list[Any] = []
            iteration_usage: TokenUsage | None = None
            incomplete_reason: str | None = None
            refusal_seen = False
            try:
                async for event in self._stream(client, selected_model, input_items, tools):
                    event_type = str(getattr(event, "type", "") or "")
                    if event_type == "response.output_text.delta":
                        delta = str(getattr(event, "delta", "") or "")
                        if delta:
                            first_token = True
                            for emitted in truncator.feed(delta):
                                yield emitted
                    elif event_type == "response.output_item.done":
                        item = getattr(event, "item", None)
                        if item is not None:
                            output_items.append(item)
                            if getattr(item, "type", "") == "function_call":
                                function_calls.append(item)
                    elif event_type in ("response.completed", "response.incomplete"):
                        response = getattr(event, "response", None)
                        if response is not None:
                            iteration_usage = add_usage(
                                TokenUsage(), getattr(response, "usage", None)
                            )
                            details = getattr(response, "incomplete_details", None)
                            incomplete_reason = (
                                getattr(details, "reason", None) if details else None
                            )
                    elif event_type in ("response.refusal.delta", "response.refusal.done"):
                        refusal_seen = True
                    elif event_type in ("response.failed", "error"):
                        code = _failure_code(event)
                        log.error(
                            "openai_stream_failed model=%s status=%s attempt=%s",
                            selected_model,
                            code,
                            retry_attempt,
                        )
                        if code in _AUTH_STATUS:
                            yield ErrorEvent(
                                message=user_facing_error(
                                    "La API key de OpenAI no es válida o no tiene permisos.",
                                    credential_remedy=_CREDENTIAL_REMEDY,
                                )
                            )
                        else:
                            yield ErrorEvent(message=_SECURITY_MESSAGE)
                        return
            except Exception as error:  # noqa: BLE001
                code = _status(error)
                if code == 429 and _quota_exhausted(error):
                    log.error("openai_quota_exhausted model=%s", selected_model)
                    yield ErrorEvent(
                        message=(
                            "La cuenta de OpenAI no tiene créditos. Un administrador "
                            "debe cargar saldo en la plataforma para que el asistente "
                            "pueda responder."
                        )
                    )
                    return
                if code in _AUTH_STATUS:
                    yield ErrorEvent(
                        message=user_facing_error(
                            "La API key de OpenAI no es válida o no tiene permisos.",
                            credential_remedy=_CREDENTIAL_REMEDY,
                        )
                    )
                    return
                if code in _RETRYABLE_STATUS and not first_token:
                    retry_attempt += 1
                    if retry_attempt <= self._settings.openai_retry_attempts:
                        log.warning(
                            "openai_retry model=%s status=%s attempt=%s",
                            selected_model,
                            code,
                            retry_attempt,
                        )
                        await asyncio.sleep(
                            self._settings.openai_retry_base_delay_s * (2 ** (retry_attempt - 1))
                        )
                        continue
                    model_index += 1
                    if model_index < len(models):
                        selected_model = models[model_index]
                        retry_attempt = 0
                        log.warning(
                            "openai_fallback model=%s status=%s", selected_model, code
                        )
                        continue
                    log.warning(
                        "openai_unavailable model=%s status=%s", selected_model, code
                    )
                    yield ErrorEvent(
                        message="No pude generar una respuesta para esa consulta."
                    )
                    return
                log.error(
                    "openai_turn_failed model=%s status=%s attempt=%s",
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

            if refusal_seen:
                # Un refusal no es una respuesta: nunca termina en DoneEvent
                # vacío, que el usuario leería como "el asistente no responde".
                log.warning("openai_refusal model=%s", selected_model)
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

            if not function_calls:
                finish = "truncated" if incomplete_reason in _TRUNCATED_REASONS else "complete"
                yield DoneEvent(
                    usage=usage.to_dict(),
                    cost_usd=compute_cost_usd(
                        usage, self._provider.pricing.get(selected_model)
                    ),
                    finish_reason=finish,
                    provider=self._provider.kind,
                    model=selected_model,
                )
                return

            # Reenviar la respuesta completa y luego cada resultado en orden.
            input_items.extend(output_items)
            for call in function_calls:
                name = str(getattr(call, "name", "") or "")
                call_id = str(getattr(call, "call_id", "") or getattr(call, "id", "") or "")
                args = _parse_arguments(getattr(call, "arguments", None))
                yield ToolUseEvent(id=call_id, name=name, input=args)
                spec = next((tool for tool in tool_specs if tool.name == name), None)
                result = await _execute_tool(spec, name, args)
                yield ToolResultEvent(tool_use_id=call_id, is_error=result.is_error)
                input_items.append(function_call_output(call_id, result))

        yield TextDeltaEvent(text="\n\nRespuesta truncada por límite de iteraciones.")
        yield DoneEvent(
            usage=usage.to_dict(),
            cost_usd=compute_cost_usd(usage, self._provider.pricing.get(selected_model)),
            finish_reason="truncated",
            provider=self._provider.kind,
            model=selected_model,
        )


def _parse_arguments(raw: object) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (ValueError, TypeError):
        return {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


async def _execute_tool(spec: ToolSpec | None, name: str, args: dict[str, Any]) -> ToolResult:
    if spec is None:
        return ToolResult(f"No existe la herramienta '{name}'.", is_error=True)
    try:
        return await spec.handler(args)
    except Exception as error:  # noqa: BLE001
        log.exception("openai_tool_failed name=%s", name)
        return ToolResult(str(error), is_error=True)
