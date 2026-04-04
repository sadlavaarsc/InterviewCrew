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
from interview_crew.config import settings


@dataclass
class StepResult:
    """Result of a single interview step."""
    agent: str
    question: str
    finished: bool
    report: str = ""
    # Token statistics for comparison testing
    token_consumed_this_turn: int = 0
    total_token_consumed: int = 0
    # Detailed breakdown by model tier
    plus_token_consumed_this_turn: int = 0  # Full model (qwen-plus)
    flash_token_consumed_this_turn: int = 0  # Downgrade model (qwen-flash)
    total_plus_token_consumed: int = 0
    total_flash_token_consumed: int = 0


class SingleAgentOrchestrator:
    """Single Agent Orchestrator - One agent handles all interview types.

    This baseline simulates the same interview flow as Multi-Agent System:
    tech1 → tech2 → sysdes → leader → hr → scribe

    By using the same stage progression, we can fairly compare:
    - MAS: 5 specialist agents with isolated memory
    - SAS: 1 agent switching roles, prone to memory/role confusion
    """

    # Same stage order as Multi-Agent System
    STAGES = ["tech1", "tech2", "sysdes", "leader", "hr"]

    # Stage descriptions for prompt injection
    STAGE_DESCRIPTIONS = {
        "tech1": "技术一面 - 基础算法与代码能力筛查",
        "tech2": "技术二面 - 深度追问、找反例、边界条件施压",
        "sysdes": "系统设计 - 系统设计与架构权衡",
        "leader": "Leader面 - 项目深挖与技术领导力",
        "hr": "HR面 - 行为面试与文化契合度"
    }

    def __init__(
        self,
        state: InterviewState,
        jd_parser=None,  # Not used in baseline, kept for interface compatibility
    ):
        self.state = state
        self.turn_count = 0
        self.llm_call_count = 0
        self.token_consumed = 0

        # Detailed token tracking by model tier
        self.total_plus_token_consumed = 0   # Full model (qwen3.5-plus)
        self.total_flash_token_consumed = 0  # Downgrade model (qwen3.5-flash)
        self.plus_call_count = 0
        self.flash_call_count = 0

        # Stage management - same as MAS
        self.current_stage_index = 0
        self.stage_turn_counts = {stage: 0 for stage in self.STAGES}

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

    def _get_current_stage(self) -> str:
        """Get current interview stage."""
        return self.STAGES[self.current_stage_index]

    def _get_stage_config(self, stage: str) -> dict:
        """Get configuration for a stage (same defaults as MAS)."""
        defaults = {
            "tech1": {"max_turns": 4},
            "tech2": {"max_turns": 4},
            "sysdes": {"max_turns": 3},
            "leader": {"max_turns": 2},
            "hr": {"max_turns": 2}
        }
        return defaults.get(stage, {"max_turns": 3})

    def step(self, candidate_response: str) -> StepResult:
        """Execute one interview step with stage progression.

        Flow: tech1 -> tech2 -> sysdes -> leader -> hr -> scribe (same as MAS)
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
                agent="scribe",
                question="",
                finished=True,
                report=report,
                token_consumed_this_turn=0,
                total_token_consumed=self.token_consumed,
                plus_token_consumed_this_turn=0,
                flash_token_consumed_this_turn=0,
                total_plus_token_consumed=self.total_plus_token_consumed,
                total_flash_token_consumed=self.total_flash_token_consumed
            )

        # 3. Determine current stage (same progression as MAS)
        current_stage = self._get_current_stage()
        self.stage_turn_counts[current_stage] += 1

        # 4. Check if we should advance to next stage
        stage_config = self._get_stage_config(current_stage)
        if self.stage_turn_counts[current_stage] >= stage_config["max_turns"]:
            if self.current_stage_index < len(self.STAGES) - 1:
                self.current_stage_index += 1
                current_stage = self._get_current_stage()
                self.stage_turn_counts[current_stage] = 1  # First turn of new stage

        # 5. Build context with stage information
        messages = self._build_messages_with_stage(current_stage)

        # 6. Estimate tokens before call
        estimated_tokens = estimate_tokens(messages)

        # 7. Call LLM (using full model - qwen-plus)
        model_used = settings.qwen_plus_model
        try:
            response = llm.invoke(messages, model_name=model_used, temperature=0.7)
            self.llm_call_count += 1
            self.plus_call_count += 1
            self.token_consumed += estimated_tokens
            self.total_plus_token_consumed += estimated_tokens
        except Exception as e:
            # Fallback to downgrade model on error
            model_used = settings.qwen_flash_model
            try:
                response = llm.invoke(messages, model_name=model_used, temperature=0.7)
                self.llm_call_count += 1
                self.flash_call_count += 1
                self.token_consumed += estimated_tokens
                self.total_flash_token_consumed += estimated_tokens
            except Exception:
                response = f"[Error generating question: {str(e)}] Could you tell me more about your technical background?"

        # 8. Update state
        self.state.unified_history.append({
            "role": "assistant",
            "content": response,
            "name": current_stage  # Tag message with stage for analysis
        })
        self.state.last_question = response
        self.state.turn = self.turn_count
        self.state.current_agent = current_stage  # Same as MAS

        # 9. Create transfer package for record
        self._create_transfer_package(response, current_stage)

        return StepResult(
            agent=current_stage,  # Return current stage as agent name (same as MAS)
            question=response,
            finished=False,
            report="",
            token_consumed_this_turn=estimated_tokens,
            total_token_consumed=self.token_consumed,
            plus_token_consumed_this_turn=estimated_tokens if model_used == settings.qwen_plus_model else 0,
            flash_token_consumed_this_turn=estimated_tokens if model_used == settings.qwen_flash_model else 0,
            total_plus_token_consumed=self.total_plus_token_consumed,
            total_flash_token_consumed=self.total_flash_token_consumed
        )

    def _build_messages_with_stage(self, current_stage: str) -> List[Dict[str, str]]:
        """Build message list with explicit stage information.

        Unlike MAS where each agent only sees their own history, SAS gives the
        single agent ALL conversation history, potentially causing role confusion.
        """
        # Build stage-specific system prompt
        stage_desc = self.STAGE_DESCRIPTIONS.get(current_stage, "面试环节")
        stage_prompt = f"""{self.system_prompt}

【当前阶段】你现在正在进行：{stage_desc}

重要提醒：
1. 你是一位面试官，现在正在扮演"{current_stage}"的角色
2. 请确保你的问题符合当前阶段的定位
3. 你可以看到之前的全部对话历史，但要注意维持当前阶段的角色一致性
4. 在阶段切换时，要主动调整提问风格和关注点
"""
        messages = [{"role": "system", "content": stage_prompt}]

        # Add context from resume and JD
        context_parts = []
        if self.state.resume_text:
            context_parts.append(f"候选人简历：\n{self.state.resume_text[:2000]}")
        if self.state.jd_text:
            context_parts.append(f"职位描述：\n{self.state.jd_text[:2000]}")

        if context_parts:
            messages.append({
                "role": "system",
                "content": "\n\n".join(context_parts)
            })

        # Add ALL conversation history (this is where role confusion can happen!)
        # Unlike MAS where agents are isolated, SAS sees everything
        history = self.state.unified_history[-15:] if len(self.state.unified_history) > 15 else self.state.unified_history
        messages.extend(history)

        # Add stage indicator with turn info
        stage_turn = self.stage_turn_counts[current_stage]
        max_turns = self.state.config.total_max_turns if self.state.config else self.state.max_turns
        messages.append({
            "role": "user",
            "content": f"[全局第 {self.turn_count}/{max_turns} 轮，当前阶段 {current_stage} 第 {stage_turn} 轮] 请继续面试。"
        })

        return messages

    def _generate_final_report(self) -> str:
        """Generate final interview report using downgrade model (flash)."""
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

        # Estimate tokens for report generation
        estimated_tokens = estimate_tokens([{"role": "user", "content": report_prompt}])

        try:
            report = llm.invoke(
                [{"role": "user", "content": report_prompt}],
                model_name=settings.qwen_flash_model,
                temperature=0.5
            )
            # Track flash model usage for report generation
            self.llm_call_count += 1
            self.flash_call_count += 1
            self.token_consumed += estimated_tokens
            self.total_flash_token_consumed += estimated_tokens
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

    def _create_transfer_package(self, question: str, stage: str) -> None:
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
            from_agent=stage,  # Track actual stage
            to_agent=stage,
            round_completed=self.turn_count,
            distillate=distillate,
            raw_digest=f"[{stage}] {question[:500]}",
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
            # Detailed breakdown by model tier
            "plus_call_count": self.plus_call_count,
            "flash_call_count": self.flash_call_count,
            "total_plus_token_consumed": self.total_plus_token_consumed,
            "total_flash_token_consumed": self.total_flash_token_consumed,
            "mode": "single_agent"
        }
