from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from interview_crew.protocol.schemas import TransferPackage, BusinessContext


Message = Dict[str, Any]  # {"role": str, "content": str, "name": Optional[str]}


@dataclass
class InterviewState:
    session_id: str
    turn: int = 0
    max_turns: int = 6

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
    hr_history: List[Message] = field(default_factory=list)
    scribe_history: List[Message] = field(default_factory=list)

    unified_history: List[Message] = field(default_factory=list)
    current_agent: str = ""  # tech1 | tech2 | sysdes | hr | scribe
    last_question: str = ""
    status: str = "ongoing"  # ongoing | finished

    # New architecture fields
    transfer_queue: List[TransferPackage] = field(default_factory=list)
    competency_history: List[Dict[str, Any]] = field(default_factory=list)
    conflict_flag: bool = False
    total_budget_consumed: int = 0

    def get_agent_history(self, agent: str) -> List[Message]:
        return getattr(self, f"{agent}_history", [])

    def append_agent_history(self, agent: str, msg: Message) -> None:
        hist = self.get_agent_history(agent)
        hist.append(msg)
        setattr(self, f"{agent}_history", hist)

    def append_unified(self, msg: Message) -> None:
        self.unified_history.append(msg)
