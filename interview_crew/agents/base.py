import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from langchain_core.runnables import RunnableLambda, RunnableSequence

from interview_crew.llm.client import llm, estimate_tokens
from interview_crew.memory.agent_mailbox import build_agent_messages
from interview_crew.protocol.schemas import AgentOutput, MemoryDistillate
from interview_crew.state import Message
from interview_crew.tools.registry import ToolPolicy, tool_registry


_DEFAULT_PROMPT_template = "你是一位面试官。请根据上下文提出一个问题。只输出合法JSON：{\"question\": \"...\", \"evaluation_score\": 0.0, \"key_weaknesses\": [], \"follow_up_candidates\": [], \"reasoning\": \"...\"}"


class BaseAgent(ABC):
    name: str = ""
    prompt_path: Optional[Path] = None
    default_temperature: float = 0.7
    preferred_model: str = ""

    def __init__(self):
        self.policy = ToolPolicy(self.name)
        if self.prompt_path and self.prompt_path.exists():
            self.system_prompt = self.prompt_path.read_text(encoding="utf-8")
        else:
            self.system_prompt = _DEFAULT_PROMPT_template
        # Build LCEL chain
        self._chain = RunnableSequence(
            RunnableLambda(self._prepare_input),
            RunnableLambda(self._llm_call),
            RunnableLambda(self._parse_output),
        )

    @abstractmethod
    def build_context(self, distillate: MemoryDistillate) -> str:
        """Convert MemoryDistillate into agent-specific context string."""
        raise NotImplementedError

    def _prepare_input(self, inputs: dict) -> dict:
        distillate: MemoryDistillate = inputs["distillate"]
        candidate_response: str = inputs.get("candidate_response", "")
        business_context: str = inputs.get("business_context", "")
        history: List[Message] = inputs.get("history", [])

        agent_context = self.build_context(distillate)
        full_system = f"{self.system_prompt}\n\n【记忆摘要】\n{agent_context}"

        messages = build_agent_messages(history, full_system, candidate_response, business_context)
        return {"messages": messages, "meta": inputs}

    def _llm_call(self, inputs: dict) -> dict:
        messages = inputs["messages"]
        meta = inputs["meta"]

        # Budget-aware model selection
        model = meta.get("forced_model") or self.preferred_model or self.policy.get_models()[0]
        temperature = meta.get("temperature", self.default_temperature)

        raw = llm.invoke(messages, model_name=model, temperature=temperature)
        return {"raw": raw, "meta": meta, "messages": messages}

    def _parse_output(self, inputs: dict) -> AgentOutput:
        raw: str = inputs["raw"]
        try:
            data = json.loads(raw.strip())
            return AgentOutput(**data)
        except Exception:
            # Fallback: wrap raw text as question
            return AgentOutput(
                question=raw.strip(),
                evaluation_score=0.5,
                key_weaknesses=[],
                follow_up_candidates=[],
                reasoning="parse failed, using raw text",
            )

    def invoke(
        self,
        distillate: MemoryDistillate,
        candidate_response: str,
        history: List[Message],
        business_context: str = "",
        forced_model: Optional[str] = None,
    ) -> AgentOutput:
        result = self._chain.invoke(
            {
                "distillate": distillate,
                "candidate_response": candidate_response,
                "history": history,
                "business_context": business_context,
                "forced_model": forced_model,
            }
        )
        return result

    def estimate_tokens(
        self,
        distillate: MemoryDistillate,
        candidate_response: str,
        history: List[Message],
        business_context: str = "",
    ) -> int:
        agent_context = self.build_context(distillate)
        full_system = f"{self.system_prompt}\n\n【记忆摘要】\n{agent_context}"
        messages = build_agent_messages(history, full_system, candidate_response, business_context)
        return estimate_tokens(messages)
