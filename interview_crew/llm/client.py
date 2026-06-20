from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage

from interview_crew.config import settings
from interview_crew.llm.model_resolver import (
    resolve_model_params,
    get_default_model,
    get_fallback_model,
)


def _build_lc_messages(messages: List[dict]) -> List[BaseMessage]:
    result: List[BaseMessage] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content, name=m.get("name")))
        else:
            result.append(HumanMessage(content=content, name=m.get("name")))
    return result


def _extract_content(msg: BaseMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return str(msg.content)


def estimate_tokens(messages: List[dict]) -> int:
    """Cheap local heuristic: characters / 4.

    NOTE: This is the legacy estimator kept for API compatibility.
    Use interview_crew.llm.token_counter for precise tiktoken counting.
    """
    total = 0
    for m in messages:
        total += len(m.get("content", ""))
    return total // 4


class LLMClient:
    """Synchronous LLM client with provider-agnostic model resolution."""

    def for_model(self, model_name: str, temperature: float = 0.7) -> ChatOpenAI:
        params = resolve_model_params(model_name)
        return ChatOpenAI(
            model=params["model"],
            api_key=params["api_key"],
            base_url=params["base_url"],
            temperature=temperature,
        )

    def invoke(
        self,
        messages: List[dict],
        model_name: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """Invoke LLM. Defaults to the configured economy-tier model."""
        model_name = model_name or get_default_model()
        lc_messages = _build_lc_messages(messages)
        llm = self.for_model(model_name, temperature)
        resp = llm.invoke(lc_messages)
        return _extract_content(resp)


llm = LLMClient()
