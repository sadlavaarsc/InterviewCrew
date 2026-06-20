"""Asynchronous LLM client with streaming support for InterviewCrew.
Provides connection pooling, SSE streaming, and metrics integration.
"""

import time
from typing import List, Optional, AsyncGenerator

from openai import AsyncOpenAI

from interview_crew.config import settings
from interview_crew.llm.model_resolver import (
    resolve_model_params,
    get_default_model,
    get_fallback_model,
)


class AsyncLLMClient:
    """Async LLM client with connection pooling and provider-agnostic resolution."""

    def __init__(self):
        self._clients: dict[str, AsyncOpenAI] = {}
        self._last_model_used: str = ""

    def _get_client(self, model_name: str) -> AsyncOpenAI:
        """Get or create cached AsyncOpenAI client for the provider."""
        params = resolve_model_params(model_name)
        provider_key = params["base_url"]  # one client per unique base_url

        if provider_key not in self._clients:
            self._clients[provider_key] = AsyncOpenAI(
                api_key=params["api_key"],
                base_url=params["base_url"],
            )
        return self._clients[provider_key]

    async def ainvoke(
        self,
        messages: List[dict],
        model_name: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """Non-blocking LLM invocation. Defaults to economy-tier model."""
        model_name = model_name or get_default_model()
        self._last_model_used = model_name

        params = resolve_model_params(model_name)
        client = self._get_client(model_name)

        start_time = time.time()
        try:
            response = await client.chat.completions.create(
                model=params["model"],
                messages=messages,
                temperature=temperature,
            )
            result = response.choices[0].message.content or ""

            latency = time.time() - start_time
            self._record_metrics(
                model_name, latency,
                getattr(response, "usage", None)
            )
            return result
        except Exception:
            fallback = get_fallback_model()
            if model_name != fallback:
                return await self.ainvoke(
                    messages,
                    model_name=fallback,
                    temperature=temperature,
                )
            raise

    async def astream(
        self,
        messages: List[dict],
        model_name: Optional[str] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream LLM response token by token. Defaults to economy-tier model."""
        model_name = model_name or get_default_model()
        self._last_model_used = model_name

        params = resolve_model_params(model_name)
        client = self._get_client(model_name)

        start_time = time.time()
        first_token_time: Optional[float] = None

        try:
            response = await client.chat.completions.create(
                model=params["model"],
                messages=messages,
                temperature=temperature,
                stream=True,
            )

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    if first_token_time is None:
                        first_token_time = time.time()
                        self._record_ttft(model_name, first_token_time - start_time)
                    yield delta.content

        except Exception as e:
            yield f"\n[Stream error: {str(e)}]"

    def _record_metrics(self, model_name: str, latency: float, usage=None):
        try:
            from interview_crew.llm.metrics import record_llm_call
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            record_llm_call(model_name, latency, input_tokens, output_tokens)
        except ImportError:
            pass

    def _record_ttft(self, model_name: str, ttft: float):
        try:
            from interview_crew.llm.metrics import record_ttft
            record_ttft(model_name, ttft)
        except ImportError:
            pass


# Global singleton
async_llm = AsyncLLMClient()
