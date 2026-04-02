from dataclasses import dataclass
from typing import List, Literal, Optional
from pathlib import Path

from interview_crew.state import InterviewState, Message
from interview_crew.protocol.schemas import (
    TransferPackage,
    MemoryDistillate,
    AgentOutput,
    BusinessContext,
)
from interview_crew.memory.distiller import distill_memory
from interview_crew.llm.client import estimate_tokens
from interview_crew.agents import Tech1Agent, Tech2Agent, SysDesAgent, HRAgent, ScribeAgent
from interview_crew.orchestrator.budget_guardian import BudgetGuardian
from interview_crew.orchestrator.conflict_arbitrator import ConflictArbitrator
from interview_crew.orchestrator.jd_parser import JDParsingStrategy, LLMJDParser


@dataclass
class StepResult:
    agent: str
    question: str
    finished: bool
    report: str = ""


_StateMachine = Literal["screening", "tech1", "tech2", "system", "hr", "finished"]


class Orchestrator:
    def __init__(
        self,
        state: InterviewState,
        jd_parser: Optional[JDParsingStrategy] = None,
    ):
        self.state = state
        self.jd_parser = jd_parser or LLMJDParser()
        self.budget_guardian = BudgetGuardian()
        self.conflict_arbitrator = ConflictArbitrator()

        self.agents = {
            "tech1": Tech1Agent(),
            "tech2": Tech2Agent(),
            "sysdes": SysDesAgent(),
            "hr": HRAgent(),
            "scribe": ScribeAgent(),
        }

        self._state_order: List[_StateMachine] = [
            "screening",
            "tech1",
            "tech2",
            "system",
            "hr",
            "finished",
        ]
        self._current_state_index = 0
        if self.state.status == "finished" or self.state.turn >= self.state.max_turns:
            self._current_state_index = len(self._state_order) - 1

        self._maybe_load_files()

    def _maybe_load_files(self) -> None:
        if self.state.resume_path and Path(self.state.resume_path).exists():
            self.state.resume_text = Path(self.state.resume_path).read_text(encoding="utf-8")
        if self.state.jd_path and Path(self.state.jd_path).exists():
            self.state.jd_text = Path(self.state.jd_path).read_text(encoding="utf-8")
            if not self.state.business_context:
                self.state.business_context = self.jd_parser.parse(self.state.jd_text)

    def _next_state(self) -> _StateMachine:
        if self.state.conflict_flag:
            # Arbitration mode: route to tech2 for reconciliation
            self.state.conflict_flag = False
            return "tech2"
        if self._current_state_index >= len(self._state_order) - 1:
            return "finished"
        state_name = self._state_order[self._current_state_index]
        self._current_state_index += 1
        return state_name

    def step(self, candidate_response: str) -> StepResult:
        self.state.candidate_response = candidate_response
        self.state.turn += 1

        # Append candidate response to unified history
        if candidate_response:
            self.state.append_unified({"role": "user", "content": candidate_response})

        # Determine next state
        next_state = self._next_state()
        if next_state == "finished" or self.state.turn >= self.state.max_turns:
            self.state.status = "finished"
            # Generate scribe report if not already done
            report = self._generate_report()
            return StepResult(agent="scribe", question="", finished=True, report=report)

        # Map state to agent
        _state_to_agent = {
            "screening": "tech1",
            "tech1": "tech2",
            "tech2": "sysdes",
            "system": "hr",
            "hr": "scribe",
        }
        agent_name = _state_to_agent.get(next_state, next_state)
        self.state.current_agent = agent_name

        # Distill memory
        memory_distillate = distill_memory(
            self.state.unified_history,
            self.state.session_id,
            self.state.turn,
        )

        # Budget check
        agent = self.agents[agent_name]
        estimated = agent.estimate_tokens(
            memory_distillate,
            candidate_response,
            self.state.get_agent_history(agent_name),
            business_context=self._business_context_text(),
        )
        forced_model = self.budget_guardian.check_and_downgrade(agent_name, estimated)

        # Invoke agent
        output = agent.invoke(
            memory_distillate,
            candidate_response,
            self.state.get_agent_history(agent_name),
            business_context=self._business_context_text(),
            forced_model=forced_model,
        )

        # Record budget
        self.budget_guardian.consume(estimated)
        self.state.total_budget_consumed += estimated

        # Update histories
        assistant_msg: Message = {
            "role": "assistant",
            "name": agent_name,
            "content": output.question,
        }
        self.state.append_agent_history(agent_name, assistant_msg)
        self.state.append_unified(assistant_msg)
        self.state.last_question = output.question

        # Update competency history
        for tag in memory_distillate.competency_vector:
            self.state.competency_history.append({
                "dimension": tag.dimension,
                "score": tag.score,
                "turn": self.state.turn,
                "agent": agent_name,
            })

        # Conflict detection
        conflict = self.conflict_arbitrator.detect_conflict(self.state.competency_history)
        if conflict:
            self.state.conflict_flag = True
            memory_distillate.contradiction_alerts.append(conflict)

        # Build TransferPackage
        pkg = TransferPackage(
            session_id=self.state.session_id,
            from_agent=agent_name,
            to_agent=self._peek_next_agent(agent_name),
            round_completed=self.state.turn,
            distillate=memory_distillate,
            raw_digest=self._digest(candidate_response, output.question),
            budget_consumed=estimated,
            challenge_flags=[conflict] if conflict else None,
            agent_question=output.question,
            evaluation_score=output.evaluation_score,
        )
        self.state.transfer_queue.append(pkg)

        return StepResult(agent=agent_name, question=output.question, finished=False)

    def _business_context_text(self) -> str:
        if not self.state.business_context:
            return ""
        ctx = self.state.business_context
        parts = [f"业务领域：{ctx.domain}"]
        if ctx.team_size:
            parts.append(f"团队规模：{ctx.team_size}")
        if ctx.tech_stack:
            parts.append(f"技术栈：{', '.join(ctx.tech_stack)}")
        if ctx.core_challenges:
            parts.append(f"核心挑战：{', '.join(ctx.core_challenges)}")
        if ctx.growth_stage:
            parts.append(f"发展阶段：{ctx.growth_stage}")
        return "\n".join(parts)

    def _peek_next_agent(self, current: str) -> str:
        mapping = {
            "tech1": "tech2",
            "tech2": "sysdes",
            "sysdes": "hr",
            "hr": "scribe",
            "scribe": "scribe",
        }
        return mapping.get(current, "scribe")

    def _digest(self, candidate_response: str, question: str) -> str:
        return f"Candidate: {candidate_response[:100]}... | Agent: {question[:100]}..."

    def _generate_report(self) -> str:
        if not self.state.transfer_queue:
            return "暂无面评数据。"

        # Use scribe agent to generate final report
        scribe = self.agents["scribe"]
        # Build a synthetic distillate from transfer queue summaries
        combined = "\n".join(
            f"Round {p.round_completed} [{p.from_agent}]: score={p.evaluation_score}, focus={p.distillate.recommended_focus}"
            for p in self.state.transfer_queue
        )
        synthetic_distillate = MemoryDistillate(
            candidate_profile={"summary": combined},
            competency_vector=[],
            doubt_list=[],
            contradiction_alerts=[],
            recommended_focus="生成最终面评报告",
        )
        output = scribe.invoke(
            synthetic_distillate,
            candidate_response=combined,
            history=self.state.get_agent_history("scribe"),
            business_context=self._business_context_text(),
        )

        # Record scribe interaction
        assistant_msg: Message = {
            "role": "assistant",
            "name": "scribe",
            "content": output.question,
        }
        self.state.append_agent_history("scribe", assistant_msg)
        self.state.append_unified(assistant_msg)
        return output.question
