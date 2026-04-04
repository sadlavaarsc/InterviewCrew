"""Single Agent Orchestrator - Baseline for comparison with Multi-Agent System."""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

from interview_crew.state import InterviewState, Message
from interview_crew.protocol.schemas import (
    TransferPackage,
    MemoryDistillate,
    AgentOutput,
    BusinessContext,
    InterviewConfig,
    CompetencyTag,
)
from interview_crew.llm.client import estimate_tokens, llm
from interview_crew.memory.distiller import distill_memory


@dataclass
class StepResult:
    """Result of a single interview step."""
    agent: str
    question: str
    finished: bool
    report: str = ""
    token_consumed_this_turn: int = 0
    total_token_consumed: int = 0


class SingleAgentOrchestrator:
    """Single Agent Orchestrator - One agent handles all interview types.

    This is a simplified baseline for comparison with the Multi-Agent System.
    It maintains the same interface as the original Orchestrator but uses
    a single agent to handle technical, system design, and behavioral questions.
    """

    def __init__(
        self,
        state: InterviewState,
        jd_parser=None,  # Not used in baseline, kept for interface compatibility
    ):
        self.state = state
        self.turn_count = 0
        self.llm_call_count = 0
        self.token_consumed = 0

        # Load prompt
        prompt_path = Path(__file__).parent / "prompts" / "single_agent.txt"
        self.system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else self._default_prompt()

    def _default_prompt(self) -> str:
        """Default prompt if file not found."""
        return """You are an experienced technical interviewer. Your role is to:
1. Assess the candidate's technical skills through coding and system design questions
2. Evaluate problem-solving abilities and depth of knowledge
3. Ask behavioral questions to understand work style and culture fit
4. Provide a comprehensive evaluation at the end

Ask one question at a time. Adapt your questions based on the candidate's responses.
Be thorough but concise."""

    def step(self, candidate_response: str) -> StepResult:
        """Execute one interview step.

        Args:
            candidate_response: The candidate's response to the previous question

        Returns:
            StepResult containing the next question and status
        """
        # 1. Update state with candidate response
        self.state.candidate_response = candidate_response
        if candidate_response:
            self.state.unified_history.append({
                "role": "user",
                "content": candidate_response
            })

        # 2. Check if interview should end
        self.turn_count += 1
        max_turns = self.state.config.total_max_turns if self.state.config else self.state.max_turns

        if self.turn_count >= max_turns:
            report = self._generate_final_report()
            return StepResult(
                agent="interviewer",
                question="",
                finished=True,
                report=report,
                token_consumed_this_turn=0,
                total_token_consumed=self.token_consumed
            )

        # 3. Build context and generate question
        messages = self._build_messages()

        # 4. Estimate tokens before call
        estimated_tokens = estimate_tokens(messages)

        # 5. Call LLM
        try:
            response = llm.invoke(messages, model_name="qwen3.5-plus", temperature=0.7)
            self.llm_call_count += 1
            self.token_consumed += estimated_tokens
        except Exception as e:
            # Fallback response
            response = f"[Error generating question: {str(e)}] Could you tell me more about your technical background?"

        # 6. Update state
        self.state.unified_history.append({
            "role": "assistant",
            "content": response
        })
        self.state.last_question = response
        self.state.turn = self.turn_count

        # 7. Create transfer package for record
        self._create_transfer_package(response)

        return StepResult(
            agent="interviewer",
            question=response,
            finished=False,
            report="",
            token_consumed_this_turn=estimated_tokens,
            total_token_consumed=self.token_consumed
        )

    def _build_messages(self) -> List[Dict[str, str]]:
        """Build message list for LLM call."""
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add context from resume and JD
        context_parts = []
        if self.state.resume_text:
            context_parts.append(f"Candidate Resume:\n{self.state.resume_text[:2000]}")
        if self.state.jd_text:
            context_parts.append(f"Job Description:\n{self.state.jd_text[:2000]}")

        if context_parts:
            messages.append({
                "role": "system",
                "content": "\n\n".join(context_parts)
            })

        # Add conversation history (last 10 messages)
        history = self.state.unified_history[-10:] if len(self.state.unified_history) > 10 else self.state.unified_history
        messages.extend(history)

        # Add turn indicator
        max_turns = self.state.config.total_max_turns if self.state.config else self.state.max_turns
        messages.append({
            "role": "user",
            "content": f"[Turn {self.turn_count}/{max_turns}] Continue the interview."
        })

        return messages

    def _generate_final_report(self) -> str:
        """Generate final interview report."""
        report_prompt = f"""Based on the following interview conversation, generate a brief evaluation report.

Conversation:
{self._format_conversation()}

Provide a concise report with:
1. Technical Assessment
2. Communication Skills
3. Overall Recommendation (Strong Hire / Hire / Weak Hire / No Hire)
4. Key Strengths
5. Areas for Improvement

Keep it brief (3-5 bullet points)."""

        try:
            report = llm.invoke(
                [{"role": "user", "content": report_prompt}],
                model_name="qwen3.5-flash",
                temperature=0.5
            )
            return report
        except Exception:
            return "Interview completed. Report generation failed."

    def _format_conversation(self) -> str:
        """Format conversation for report generation."""
        lines = []
        for msg in self.state.unified_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"Candidate: {content}")
            elif role == "assistant":
                lines.append(f"Interviewer: {content}")
        return "\n\n".join(lines[-20:])  # Last 20 exchanges

    def _create_transfer_package(self, question: str) -> None:
        """Create a transfer package for record keeping."""
        # Simplified distillate for baseline
        distillate = MemoryDistillate(
            candidate_profile={},
            competency_vector=[],
            doubt_list=[],
            recommended_focus=""
        )

        package = TransferPackage(
            session_id=self.state.session_id,
            from_agent="interviewer",
            to_agent="interviewer",
            round_completed=self.turn_count,
            distillate=distillate,
            raw_digest=question[:500],
            budget_consumed=self.token_consumed,
            agent_question=question
        )

        self.state.transfer_queue.append(package)

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics for comparison testing."""
        return {
            "turn_count": self.turn_count,
            "llm_call_count": self.llm_call_count,
            "token_consumed": self.token_consumed,
            "mode": "single_agent"
        }
