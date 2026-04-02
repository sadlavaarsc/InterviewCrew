from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from interview_crew.config import settings


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
    """Cheap local heuristic: characters / 4."""
    total = 0
    for m in messages:
        total += len(m.get("content", ""))
    return total // 4


def _resolve_model_params(model_name: str) -> dict:
    """Map model alias to API key / base_url / actual model name."""
    if model_name == settings.qwen_flash_model:
        return {
            "model": settings.dashscope_model,
            "api_key": settings.dashscope_api_key,
            "base_url": settings.dashscope_base_url,
        }
    if model_name == settings.qwen_plus_model:
        # If qwen-plus is also on dashscope, reuse same creds for now.
        # Can be re-routed to ark or another provider later.
        return {
            "model": model_name,
            "api_key": settings.dashscope_api_key,
            "base_url": settings.dashscope_base_url,
        }
    # fallback to ark
    return {
        "model": settings.ark_model,
        "api_key": settings.ark_api_key,
        "base_url": settings.ark_base_url,
    }


class LLMClient:
    def for_model(self, model_name: str, temperature: float = 0.7) -> ChatOpenAI:
        params = _resolve_model_params(model_name)
        return ChatOpenAI(
            model=params["model"],
            api_key=params["api_key"],
            base_url=params["base_url"],
            temperature=temperature,
        )

    def invoke(self, messages: List[dict], model_name: Optional[str] = None, temperature: float = 0.7) -> str:
        model_name = model_name or settings.qwen_flash_model
        lc_messages = _build_lc_messages(messages)
        llm = self.for_model(model_name, temperature)
        resp = llm.invoke(lc_messages)
        return _extract_content(resp)


llm = LLMClient()
