from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from interview_crew.protocol.schemas import TransferPackage, BusinessContext, CodingProblem, InterviewConfig


Message = Dict[str, Any]  # {"role": str, "content": str, "name": Optional[str]}


@dataclass
class InterviewState:
    session_id: str
    turn: int = 0
    max_turns: int = 6  # Deprecated: use config.total_max_turns instead

    # Interview configuration (new)
    config: InterviewConfig = field(default_factory=InterviewConfig)

    candidate_response: str = ""

    # External file paths
    resume_path: Optional[str] = None
    jd_path: Optional[str] = None
    resume_text: str = ""
    jd_text: str = ""

    # Parsed business context from JD
    business_context: Optional[BusinessContext] = None

    # Agent private histories
    tech1_history: List[Message] = field(default_factory=list)
    tech2_history: List[Message] = field(default_factory=list)
    sysdes_history: List[Message] = field(default_factory=list)
    leader_history: List[Message] = field(default_factory=list)  # New: Leader agent history
    hr_history: List[Message] = field(default_factory=list)
    scribe_history: List[Message] = field(default_factory=list)

    unified_history: List[Message] = field(default_factory=list)
    current_agent: str = ""  # tech1 | tech2 | sysdes | leader | hr | scribe
    last_question: str = ""
    status: str = "ongoing"  # ongoing | finished

    # New architecture fields
    transfer_queue: List[TransferPackage] = field(default_factory=list)
    competency_history: List[Dict[str, Any]] = field(default_factory=list)
    conflict_flag: bool = False
    total_budget_consumed: int = 0

    # Persistent round tracking for orchestrator session recovery
    round_turn_counts: Dict[str, int] = field(default_factory=dict)
    current_round_index: int = 0

    # Sub-stage management for Tech Agents
    tech1_sub_stage: str = "chat"  # chat -> coding -> reflect -> done
    tech2_sub_stage: str = "chat"

    # Current coding task (shared between Tech agents and API)
    current_coding_task: Optional[Dict[str, Any]] = None

    # Sub-stage counters (to track how many turns in each stage)
    tech1_stage_turns: int = 0
    tech2_stage_turns: int = 0

    def get_agent_history(self, agent: str) -> List[Message]:
        return getattr(self, f"{agent}_history", [])

    def append_agent_history(self, agent: str, msg: Message) -> None:
        hist = self.get_agent_history(agent)
        hist.append(msg)
        setattr(self, f"{agent}_history", hist)

    def append_unified(self, msg: Message) -> None:
        self.unified_history.append(msg)

    # ========== Sub-stage Management ==========

    def get_sub_stage(self, agent: str) -> str:
        """Get current sub-stage for a Tech Agent."""
        return getattr(self, f"{agent}_sub_stage", "chat")

    def set_sub_stage(self, agent: str, stage: str) -> None:
        """Set sub-stage for a Tech Agent."""
        setattr(self, f"{agent}_sub_stage", stage)

    def advance_sub_stage(self, agent: str) -> str:
        """Advance to next sub-stage. Returns the new stage."""
        stages = ["chat", "coding", "reflect", "done"]
        current = self.get_sub_stage(agent)
        if current in stages:
            idx = stages.index(current)
            if idx < len(stages) - 1:
                next_stage = stages[idx + 1]
                self.set_sub_stage(agent, next_stage)
                # Reset stage turn counter
                setattr(self, f"{agent}_stage_turns", 0)
                return next_stage
        return "done"

    def get_stage_turns(self, agent: str) -> int:
        """Get number of turns in current sub-stage."""
        return getattr(self, f"{agent}_stage_turns", 0)

    def increment_stage_turns(self, agent: str) -> None:
        """Increment turn counter for current sub-stage."""
        current = getattr(self, f"{agent}_stage_turns", 0)
        setattr(self, f"{agent}_stage_turns", current + 1)

    def should_advance_stage(self, agent: str, max_chat_turns: int = 2, max_reflect_turns: int = 1) -> bool:
        """
        Determine if should advance to next sub-stage based on turn count.
        - chat stage: max_chat_turns (default 2)
        - coding stage: always wait for code submission (manual trigger)
        - reflect stage: max_reflect_turns (default 1)
        """
        stage = self.get_sub_stage(agent)
        turns = self.get_stage_turns(agent)

        if stage == "chat" and turns >= max_chat_turns:
            return True
        elif stage == "reflect" and turns >= max_reflect_turns:
            return True
        # coding stage requires manual trigger via code submission
        return False

    def reset_agent_stage(self, agent: str) -> None:
        """Reset sub-stage to initial state for an agent."""
        self.set_sub_stage(agent, "chat")
        setattr(self, f"{agent}_stage_turns", 0)
