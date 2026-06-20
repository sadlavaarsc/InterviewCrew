import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any

from langchain_core.runnables import RunnableLambda, RunnableSequence

from interview_crew.llm.client import llm
from interview_crew.llm.token_counter import estimate_tokens
from interview_crew.memory.agent_mailbox import build_agent_messages
from interview_crew.protocol.schemas import AgentOutput, MemoryDistillate, CodingProblem, ExecutionResult, TestResult
from interview_crew.state import Message, InterviewState
from interview_crew.tools.registry import ToolPolicy, tool_registry
from interview_crew.services.code_sandbox import code_sandbox


_DEFAULT_PROMPT_template = "你是一位面试官。请根据上下文提出一个问题。只输出合法JSON：{\"question\": \"...\", \"evaluation_score\": 0.0, \"key_weaknesses\": [], \"follow_up_candidates\": [], \"reasoning\": \"...\"}"


class BaseAgent(ABC):
    name: str = ""
    prompt_path: Optional[Path] = None
    default_temperature: float = 0.7
    preferred_model: str = ""

    # Sub-stage management (for Tech Agents)
    has_sub_stages: bool = False
    sub_stages: List[str] = ["chat", "coding", "reflect"]

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

    # ========== Sub-stage Management (for Tech Agents) ==========

    def build_coding_context(self, distillate: MemoryDistillate, state: InterviewState) -> str:
        """Build context for coding stage. Override in Tech Agents."""
        return "Coding stage context not implemented"

    def build_reflect_context(self, distillate: MemoryDistillate, state: InterviewState) -> str:
        """Build context for reflect stage. Override in Tech Agents."""
        return "Reflect stage context not implemented"

    def generate_coding_problem(self, distillate: MemoryDistillate, difficulty: str = "easy") -> CodingProblem:
        """Generate a coding problem. Override in Tech Agents."""
        # Default implementation uses sandbox problem bank
        return code_sandbox.generate_problem(["python"], difficulty)

    def handle_code_submission(
        self,
        code: str,
        problem: CodingProblem,
        state: InterviewState
    ) -> ExecutionResult:
        """Handle code submission and return execution result."""
        result = code_sandbox.execute(
            code,
            [tc.model_dump() for tc in problem.test_cases],
            language="python"
        )
        return result

    def generate_coding_follow_up(
        self,
        result: ExecutionResult,
        problem: CodingProblem
    ) -> str:
        """Generate follow-up question based on code execution result."""
        if result.overall_passed:
            return "代码通过了所有测试用例。能否分析一下你的解法的时间复杂度和空间复杂度？有没有优化的空间？"
        else:
            failed = [tr for tr in result.test_results if not tr.passed]
            return f"代码未能通过所有测试用例（{len(failed)} 个失败）。请检查一下边界情况或逻辑错误，然后告诉我你的修复思路。"

    def _prepare_input(self, inputs: dict) -> dict:
        distillate: MemoryDistillate = inputs["distillate"]
        candidate_response: str = inputs.get("candidate_response", "")
        business_context: str = inputs.get("business_context", "")
        history: List[Message] = inputs.get("history", [])
        resume_context: str = inputs.get("resume_context", "")

        agent_context = self.build_context(distillate)
        full_system = f"{self.system_prompt}\n\n【记忆摘要】\n{agent_context}"

        messages = build_agent_messages(
            history, full_system, candidate_response, business_context, resume_context
        )
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
            # Handle CodingProblem and ExecutionResult nested structures
            if "coding_problem" in data and data["coding_problem"]:
                problem_data = data["coding_problem"]
                from interview_crew.protocol.schemas import TestCase
                test_cases = [
                    TestCase(**tc) if isinstance(tc, dict) else tc
                    for tc in problem_data.get("test_cases", [])
                ]
                problem_data["test_cases"] = test_cases
                data["coding_problem"] = CodingProblem(**problem_data)
            if "code_execution_result" in data and data["code_execution_result"]:
                result_data = data["code_execution_result"]
                test_results = [
                    TestResult(**tr) if isinstance(tr, dict) else tr
                    for tr in result_data.get("test_results", [])
                ]
                result_data["test_results"] = test_results
                data["code_execution_result"] = ExecutionResult(**result_data)
            return AgentOutput(**data)
        except Exception as e:
            # Fallback: wrap raw text as question
            return AgentOutput(
                question=raw.strip(),
                evaluation_score=0.5,
                key_weaknesses=[],
                follow_up_candidates=[],
                reasoning=f"parse failed ({str(e)}), using raw text",
            )

    def invoke(
        self,
        distillate: MemoryDistillate,
        candidate_response: str,
        history: List[Message],
        business_context: str = "",
        forced_model: Optional[str] = None,
        resume_context: str = "",
    ) -> AgentOutput:
        result = self._chain.invoke(
            {
                "distillate": distillate,
                "candidate_response": candidate_response,
                "history": history,
                "business_context": business_context,
                "forced_model": forced_model,
                "resume_context": resume_context,
            }
        )
        return result

    def estimate_tokens(
        self,
        distillate: MemoryDistillate,
        candidate_response: str,
        history: List[Message],
        business_context: str = "",
        resume_context: str = "",
    ) -> int:
        agent_context = self.build_context(distillate)
        full_system = f"{self.system_prompt}\n\n【记忆摘要】\n{agent_context}"
        messages = build_agent_messages(history, full_system, candidate_response, business_context, resume_context)
        return estimate_tokens(messages)
