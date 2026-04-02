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
    # some models return list of dicts
    return str(msg.content)


class LLMClient:
    def __init__(self):
        self.primary = ChatOpenAI(
            model=settings.ark_model,
            api_key=settings.ark_api_key,
            base_url=settings.ark_base_url,
            temperature=0.7,
        )
        self.fallback = ChatOpenAI(
            model=settings.dashscope_model,
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            temperature=0.7,
        )

    def invoke(self, messages: List[dict]) -> str:
        lc_messages = _build_lc_messages(messages)
        try:
            resp = self.primary.invoke(lc_messages)
            return _extract_content(resp)
        except Exception as e:
            print(f"[LLM] Primary API failed: {e}, trying fallback...")
            resp = self.fallback.invoke(lc_messages)
            return _extract_content(resp)


llm = LLMClient()
