"""Single Interview Agent - One agent handles all interview types."""

from pathlib import Path
from typing import List, Optional, Dict, Any

from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import AgentOutput, MemoryDistillate
from interview_crew.state import Message, InterviewState
from interview_crew.llm.client import llm, estimate_tokens
from interview_crew.llm.model_resolver import get_premium_model


class SingleInterviewAgent(BaseAgent):
    """Single Interview Agent - Handles technical, system design, and behavioral questions.

    This is a simplified agent for the Single Agent Baseline that combines
    the capabilities of all specialist agents into one.
    """

    name = "single_interviewer"
    prompt_path = Path(__file__).parent / "prompts" / "single_agent.txt"
    preferred_model = get_premium_model()
    default_temperature = 0.7

    def build_context(self, distillate: MemoryDistillate) -> str:
        """Build simplified context from distillate.

        For the single agent baseline, we keep the context simple and
        let the agent infer what type of question to ask based on
        conversation flow.
        """
        context_parts = []

        # Add competency vector if available
        if distillate.competency_vector:
            context_parts.append("已评估能力维度:")
            for tag in distillate.competency_vector:
                context_parts.append(f"  - {tag.dimension}: {tag.score:.2f}")

        # Add candidate profile if available
        if distillate.candidate_profile:
            context_parts.append("\n候选人画像:")
            for key, value in distillate.candidate_profile.items():
                context_parts.append(f"  - {key}: {value}")

        # Add doubts if any
        if distillate.doubt_list:
            context_parts.append("\n需要追问的疑点:")
            for doubt in distillate.doubt_list:
                context_parts.append(f"  - {doubt}")

        # Add recommended focus
        if distillate.recommended_focus:
            context_parts.append(f"\n建议追问方向: {distillate.recommended_focus}")

        return "\n".join(context_parts) if context_parts else "暂无需特别关注的记忆摘要。"

    def invoke_simple(
        self,
        history: List[Message],
        resume: str = "",
        jd: str = "",
        turn: int = 0,
        max_turns: int = 30,
    ) -> AgentOutput:
        """Simplified invoke method for single agent baseline.

        This is a simplified version that doesn't use the full LCEL chain
        but maintains compatibility with the expected output format.
        """
        # Build messages
        messages = self._build_messages_simple(history, resume, jd, turn, max_turns)

        # Call LLM
        try:
            response = llm.invoke(messages, model_name=self.preferred_model, temperature=self.default_temperature)
        except Exception as e:
            return AgentOutput(
                question=f"[Error: {str(e)}] 能否介绍一下你的技术背景？",
                evaluation_score=0.5,
                key_weaknesses=[],
                follow_up_candidates=[],
                reasoning="LLM call failed, using fallback",
            )

        # Parse output
        return self._parse_simple(response)

    def _build_messages_simple(
        self,
        history: List[Message],
        resume: str,
        jd: str,
        turn: int,
        max_turns: int,
    ) -> List[Dict[str, str]]:
        """Build message list for simple invoke."""
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add context from resume and JD
        context_parts = []
        if resume:
            context_parts.append(f"候选人简历（摘要）:\n{resume[:1500]}")
        if jd:
            context_parts.append(f"职位描述（摘要）:\n{jd[:1500]}")

        if context_parts:
            messages.append({
                "role": "system",
                "content": "\n\n".join(context_parts)
            })

        # Add conversation history (last 10 messages)
        recent_history = history[-10:] if len(history) > 10 else history
        messages.extend(recent_history)

        # Add turn indicator for the agent
        progress = f"[面试进度: 第 {turn} 轮 / 共约 {max_turns} 轮]"
        if turn == 1:
            messages.append({
                "role": "user",
                "content": f"{progress} 这是面试的开始，请向候选人打招呼并询问他们的技术背景。"
            })
        elif turn == max_turns:
            messages.append({
                "role": "user",
                "content": f"{progress} 这是最后一轮，请进行总结并感谢候选人。"
            })
        else:
            messages.append({
                "role": "user",
                "content": f"{progress} 基于对话历史，提出下一个面试问题。可以涉及技术、系统设计或行为问题。"
            })

        return messages

    def _parse_simple(self, raw: str) -> AgentOutput:
        """Parse LLM output into AgentOutput."""
        import json

        try:
            # Try to parse as JSON
            data = json.loads(raw.strip())
            return AgentOutput(
                question=data.get("question", raw.strip()),
                evaluation_score=data.get("evaluation_score", 0.5),
                key_weaknesses=data.get("key_weaknesses", []),
                follow_up_candidates=data.get("follow_up_candidates", []),
                reasoning=data.get("reasoning", ""),
            )
        except json.JSONDecodeError:
            # Fallback: use raw text as question
            return AgentOutput(
                question=raw.strip(),
                evaluation_score=0.5,
                key_weaknesses=[],
                follow_up_candidates=[],
                reasoning="JSON parse failed, using raw text",
            )

    def estimate_tokens_simple(
        self,
        history: List[Message],
        resume: str = "",
        jd: str = "",
    ) -> int:
        """Estimate tokens for simple invoke."""
        messages = self._build_messages_simple(history, resume, jd, 1, 30)
        return estimate_tokens(messages)
