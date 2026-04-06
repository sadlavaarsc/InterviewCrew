from dataclasses import dataclass
from typing import List, Literal, Optional, Dict
from pathlib import Path

from interview_crew.state import InterviewState, Message
from interview_crew.protocol.schemas import (
    TransferPackage,
    MemoryDistillate,
    AgentOutput,
    BusinessContext,
    InterviewConfig,
    InterviewRoundConfig,
)
from interview_crew.memory.distiller import distill_memory
from interview_crew.llm.client import estimate_tokens
from interview_crew.agents import Tech1Agent, Tech2Agent, SysDesAgent, LeaderAgent, HRAgent, ScribeAgent
from interview_crew.orchestrator.budget_guardian import BudgetGuardian
from interview_crew.orchestrator.conflict_arbitrator import ConflictArbitrator
from interview_crew.orchestrator.jd_parser import JDParsingStrategy, LLMJDParser


@dataclass
class StepResult:
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


_StateMachine = Literal["screening", "tech1", "tech2", "system", "leader", "hr", "finished"]


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
            "leader": LeaderAgent(),
            "hr": HRAgent(),
            "scribe": ScribeAgent(),
        }

        # New: Use config to determine enabled rounds and order
        self._enabled_rounds = self.state.config.get_enabled_rounds()

        # Load persistent round tracking from state
        self._round_turn_counts: Dict[str, int] = getattr(
            self.state, "round_turn_counts", {}
        )

        # Determine _current_round_index: if current agent has already started
        # (has turn count > 0), index should point to the NEXT agent.
        has_agent_started = (
            self.state.current_agent in self._round_turn_counts
            and self._round_turn_counts[self.state.current_agent] > 0
        )
        if has_agent_started and self.state.current_agent in self._enabled_rounds:
            self._current_round_index = (
                self._enabled_rounds.index(self.state.current_agent) + 1
            )
        else:
            self._current_round_index = getattr(
                self.state, "current_round_index", self._get_current_round_index()
            )

        if self.state.status == "finished" or self.state.turn >= self._get_effective_max_turns():
            self._current_round_index = len(self._enabled_rounds)

        self._maybe_load_files()

    def _get_current_round_index(self) -> int:
        """Get the index of current agent in enabled rounds."""
        if not self.state.current_agent:
            return 0
        if self.state.current_agent in self._enabled_rounds:
            return self._enabled_rounds.index(self.state.current_agent)
        # If current agent not in enabled rounds (e.g., just finished one), find next
        return len(self._enabled_rounds)

    def _get_effective_max_turns(self) -> int:
        """Get effective max turns (config takes precedence over legacy)."""
        return self.state.config.total_max_turns if self.state.config else self.state.max_turns

    def _maybe_load_files(self) -> None:
        try:
            if self.state.resume_path and Path(self.state.resume_path).exists():
                self.state.resume_text = Path(self.state.resume_path).read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError) as e:
            self.state.resume_text = f""
        try:
            if self.state.jd_path and Path(self.state.jd_path).exists():
                self.state.jd_text = Path(self.state.jd_path).read_text(encoding="utf-8")
                if not self.state.business_context:
                    self.state.business_context = self.jd_parser.parse(self.state.jd_text)
        except (IOError, UnicodeDecodeError) as e:
            self.state.jd_text = ""

    def _next_agent(self) -> str:
        """Determine next agent based on config-enabled rounds.

        Returns "scribe" if no more rounds, or the next enabled agent name.
        """
        if self.state.conflict_flag:
            # Arbitration mode: route to tech2 for reconciliation
            self.state.conflict_flag = False
            if "tech2" in self._enabled_rounds:
                return "tech2"

        if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
            round_config = self.state.config.get_round_config(self.state.current_agent)
            current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)

            if self.state.current_agent in ["tech1", "tech2"]:
                # Tech Agent: only advance if sub_stage is done AND turns exhausted
                if self.state.get_sub_stage(self.state.current_agent) != "done":
                    return self.state.current_agent
                if current_round_turns < round_config.max_turns:
                    return self.state.current_agent
            else:
                # Non-tech Agent: advance only when turns exhausted
                if current_round_turns < round_config.max_turns:
                    return self.state.current_agent

        # Advance to next round
        if self._current_round_index >= len(self._enabled_rounds):
            return "scribe"

        next_agent = self._enabled_rounds[self._current_round_index]
        self._current_round_index += 1
        return next_agent

    def step(self, candidate_response: str) -> StepResult:
        self.state.candidate_response = candidate_response
        self.state.turn += 1

        # Append candidate response to unified history
        if candidate_response:
            self.state.append_unified({"role": "user", "content": candidate_response})

        # Global turn limit check (applies even during sub-stages)
        effective_max_turns = self._get_effective_max_turns()
        if self.state.turn >= effective_max_turns:
            self.state.status = "finished"
            report = self._generate_report()
            return StepResult(agent="scribe", question="", finished=True, report=report)

        # Check if current agent has sub-stages and is not done
        if self.state.current_agent in ["tech1", "tech2"]:
            agent_name = self.state.current_agent
            agent = self.agents[agent_name]

            if agent.has_sub_stages:
                sub_stage = self.state.get_sub_stage(agent_name)

                if sub_stage != "done":
                    # Process sub-stage
                    return self._process_tech_agent_sub_stage(agent_name, candidate_response)
                else:
                    # Sub-stages complete, advance to next main state
                    pass

        # Track per-round turn count for current agent BEFORE calling _next_agent()
        # This ensures _next_agent() sees the updated count when deciding whether to advance
        if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
            self._round_turn_counts[self.state.current_agent] = self._round_turn_counts.get(self.state.current_agent, 0) + 1
            # Persist to state for session recovery
            self.state.round_turn_counts = self._round_turn_counts

        # Determine next agent
        next_agent = self._next_agent()
        # Persist round index to state for session recovery
        self.state.current_round_index = self._current_round_index

        if next_agent == "scribe" or self.state.turn >= effective_max_turns:
            self.state.status = "finished"
            report = self._generate_report()
            return StepResult(agent="scribe", question="", finished=True, report=report)

        self.state.current_agent = next_agent

        # Check if this is a Tech Agent with sub-stages
        agent = self.agents[next_agent]
        if agent.has_sub_stages:
            # Reset sub-stage to beginning (needed when continuing same agent for next round)
            self.state.reset_agent_stage(next_agent)
            return self._process_tech_agent_sub_stage(next_agent, candidate_response)

        return self._process_standard_agent(next_agent, candidate_response)

    def _process_tech_agent_sub_stage(self, agent_name: str, candidate_response: str) -> StepResult:
        """Process Tech Agent with sub-stages (chat -> coding -> reflect)."""
        # Check global turn limit first (fixes BUG-001)
        effective_max_turns = self._get_effective_max_turns()
        if self.state.turn >= effective_max_turns:
            self.state.status = "finished"
            report = self._generate_report()
            return StepResult(agent="scribe", question="", finished=True, report=report)

        agent = self.agents[agent_name]
        sub_stage = self.state.get_sub_stage(agent_name)

        # Distill memory
        memory_distillate = distill_memory(
            self.state.unified_history,
            self.state.session_id,
            self.state.turn,
        )

        # Build context based on sub-stage
        if sub_stage == "chat":
            context = agent.build_context(memory_distillate)
        elif sub_stage == "coding":
            context = agent.build_coding_context(memory_distillate, self.state)
            # If entering coding stage, generate a problem
            if self.state.get_stage_turns(agent_name) == 0:
                difficulty = "easy" if agent_name == "tech1" else "medium"
                problem = agent.generate_coding_problem(memory_distillate, difficulty)
                if problem is None:
                    self.state.current_coding_task = None
                elif hasattr(problem, "model_dump"):
                    self.state.current_coding_task = problem.model_dump()
                else:
                    self.state.current_coding_task = problem.to_dict()
        elif sub_stage == "reflect":
            context = agent.build_reflect_context(memory_distillate, self.state)
            # Clear coding task
            self.state.current_coding_task = None
        else:
            context = agent.build_context(memory_distillate)

        # Budget check
        estimated = agent.estimate_tokens(
            memory_distillate,
            candidate_response,
            self.state.get_agent_history(agent_name),
            business_context=self._business_context_text(),
            resume_context=self.state.resume_text,
        )
        forced_model = self.budget_guardian.check_and_downgrade(agent_name, estimated)

        # Create temporary system prompt with sub-stage context
        from interview_crew.memory.agent_mailbox import build_agent_messages
        messages = build_agent_messages(
            self.state.get_agent_history(agent_name),
            f"{agent.system_prompt}\n\n【当前阶段】\n{context}",
            candidate_response,
            self._business_context_text(),
            self.state.resume_text,
        )

        # Invoke LLM
        from interview_crew.llm.client import llm
        raw = llm.invoke(messages, model_name=forced_model or agent.preferred_model, temperature=agent.default_temperature)

        # Parse output
        try:
            import json
            data = json.loads(raw.strip())
            from interview_crew.protocol.schemas import TestCase, CodingProblem
            if "coding_problem" in data and data["coding_problem"]:
                problem_data = data["coding_problem"]
                test_cases = [TestCase(**tc) if isinstance(tc, dict) else tc for tc in problem_data.get("test_cases", [])]
                problem_data["test_cases"] = test_cases
                data["coding_problem"] = CodingProblem(**problem_data)
                # Update current coding task
                self.state.current_coding_task = data["coding_problem"].model_dump()
            from interview_crew.protocol.schemas import AgentOutput
            output = AgentOutput(**data)
        except Exception as e:
            from interview_crew.protocol.schemas import AgentOutput
            output = AgentOutput(
                question=raw.strip(),
                evaluation_score=0.5,
                key_weaknesses=[],
                follow_up_candidates=[],
                reasoning=f"parse error: {str(e)}",
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

        # Update sub-stage turn counter
        self.state.increment_stage_turns(agent_name)

        # Check if should advance sub-stage (use config limits)
        round_config = self.state.config.get_round_config(agent_name)
        if sub_stage == "chat" and self.state.get_stage_turns(agent_name) >= round_config.max_chat_turns:
            self.state.advance_sub_stage(agent_name)
        elif sub_stage == "coding":
            # coding stage waits for manual code submission via API
            pass
        elif sub_stage == "reflect" and self.state.get_stage_turns(agent_name) >= round_config.max_reflect_turns:
            self.state.advance_sub_stage(agent_name)

        # Build TransferPackage
        conflict = self.conflict_arbitrator.detect_conflict(self.state.competency_history)
        if conflict:
            self.state.conflict_flag = True
            memory_distillate.contradiction_alerts.append(conflict)

        pkg = TransferPackage(
            session_id=self.state.session_id,
            from_agent=agent_name,
            to_agent=self._peek_next_agent(agent_name),
            round_completed=self.state.turn,
            distillate=memory_distillate,
            raw_digest=self._digest(candidate_response, output.question),
            budget_consumed=estimated,
            challenge_flags=[conflict] if conflict else [],
            agent_question=output.question,
            evaluation_score=output.evaluation_score,
        )
        self.state.transfer_queue.append(pkg)

        return StepResult(agent=agent_name, question=output.question, finished=False)

    def _process_standard_agent(self, agent_name: str, candidate_response: str) -> StepResult:
        """Process standard agent without sub-stages."""
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
            resume_context=self.state.resume_text,
        )
        forced_model = self.budget_guardian.check_and_downgrade(agent_name, estimated)

        # Invoke agent
        output = agent.invoke(
            memory_distillate,
            candidate_response,
            self.state.get_agent_history(agent_name),
            business_context=self._business_context_text(),
            forced_model=forced_model,
            resume_context=self.state.resume_text,
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
            challenge_flags=[conflict] if conflict else [],
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
        """Peek next agent based on config-enabled rounds.

        Considers remaining turns for the current agent.
        """
        if current == "scribe":
            return "scribe"

        if current in self._enabled_rounds:
            round_config = self.state.config.get_round_config(current)
            current_round_turns = self._round_turn_counts.get(current, 0)
            # If current agent still has remaining turns, next is itself
            if current_round_turns < round_config.max_turns:
                return current
            # Otherwise advance to next enabled round
            idx = self._enabled_rounds.index(current)
            if idx + 1 < len(self._enabled_rounds):
                return self._enabled_rounds[idx + 1]

        return "scribe"

    def _digest(self, candidate_response: str, question: str) -> str:
        return f"Candidate: {candidate_response[:100]}... | Agent: {question[:100]}..."

    def _build_scribe_context(self) -> str:
        """构建供 Scribe 使用的完整面试上下文。

        聚合所有 TransferPackage 的详细信息、unified_history 对话记录，
        确保 Scribe 有充足的证据支撑面评报告。
        """
        context_parts = []

        # 1. 面试轮次摘要（详细版）
        context_parts.append("【面试轮次详情】")
        for p in self.state.transfer_queue:
            context_parts.append(f"\n=== 第 {p.round_completed} 轮 [{p.from_agent}] ===")
            context_parts.append(f"问题: {p.agent_question or 'N/A'}")
            context_parts.append(f"评分: {p.evaluation_score if p.evaluation_score is not None else 'N/A'}")
            context_parts.append(f"对话摘要: {p.raw_digest}")

            # 添加该轮的 distillate 详情
            d = p.distillate
            if d.candidate_profile:
                context_parts.append("候选人画像更新:")
                for key, value in d.candidate_profile.items():
                    context_parts.append(f"  - {key}: {value}")

            if d.competency_vector:
                context_parts.append("能力维度评估:")
                for tag in d.competency_vector:
                    context_parts.append(
                        f"  - {tag.dimension}: {tag.score:.2f}分 (置信度: {tag.confidence:.2f})"
                    )
                    context_parts.append(f"    证据: {tag.evidence}")

            if d.doubt_list:
                context_parts.append(f"质疑点: {', '.join(d.doubt_list)}")

            if d.contradiction_alerts:
                context_parts.append(f"冲突警告: {', '.join(d.contradiction_alerts)}")

            if d.recommended_focus:
                context_parts.append(f"推荐关注点: {d.recommended_focus}")

            if p.challenge_flags:
                context_parts.append(f"挑战标记: {', '.join(p.challenge_flags)}")
        context_parts.append("")

        # 2. 完整对话历史
        if self.state.unified_history:
            context_parts.append("【完整对话历史】")
            for msg in self.state.unified_history:
                role = msg.get("role", "unknown")
                name = msg.get("name", "")
                content = msg.get("content", "")

                if role == "assistant" and name:
                    context_parts.append(f"[{name}] {content}")
                elif role == "user":
                    context_parts.append(f"[候选人] {content}")
                else:
                    context_parts.append(f"[{role}] {content}")
            context_parts.append("")

        # 3. 能力历史聚合
        if self.state.competency_history:
            context_parts.append("【能力评分历史】")
            for entry in self.state.competency_history:
                context_parts.append(
                    f"- 第{entry['turn']}轮 [{entry['agent']}]: "
                    f"{entry['dimension']} = {entry['score']:.2f}"
                )
            context_parts.append("")

        return "\n".join(context_parts)

    def _generate_report(self) -> str:
        if not self.state.transfer_queue:
            return "暂无面评数据。"

        # Use scribe agent to generate final report
        scribe = self.agents["scribe"]

        # 构建完整的面试上下文
        full_context = self._build_scribe_context()

        # 构建聚合的 distillate，保留所有关键信息
        all_competency_vectors = []
        all_doubts = []
        all_alerts = []
        candidate_profile_summary = {}

        for p in self.state.transfer_queue:
            d = p.distillate
            all_competency_vectors.extend(d.competency_vector)
            all_doubts.extend(d.doubt_list)
            all_alerts.extend(d.contradiction_alerts)
            if d.candidate_profile:
                candidate_profile_summary.update(d.candidate_profile)

        synthetic_distillate = MemoryDistillate(
            candidate_profile=candidate_profile_summary or {"面试轮数": str(len(self.state.transfer_queue))},
            competency_vector=all_competency_vectors,
            doubt_list=list(set(all_doubts)),  # 去重
            contradiction_alerts=list(set(all_alerts)),  # 去重
            recommended_focus="基于完整面试记录生成最终面评报告",
        )

        output = scribe.invoke(
            synthetic_distillate,
            candidate_response=full_context,  # 传递完整的上下文作为 candidate_response
            history=self.state.get_agent_history("scribe"),
            business_context=self._business_context_text(),
            resume_context=self.state.resume_text,
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
