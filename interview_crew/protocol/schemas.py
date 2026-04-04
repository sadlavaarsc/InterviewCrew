from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Dict, Any


# ==================== Interview Configuration ====================

class InterviewRoundConfig(BaseModel):
    """Configuration for a single interview round (Agent).

    Controls how many turns each agent gets and whether they are enabled.

    Example:
        {
            "tech1": {"enabled": True, "max_turns": 4},
            "tech2": {"enabled": True, "max_turns": 4},
            "sysdes": {"enabled": False},  # Skip this round
            "leader": {"enabled": True, "max_turns": 2},
            "hr": {"enabled": True, "max_turns": 2}
        }
    """
    enabled: bool = Field(default=True, description="Whether this round is enabled")
    max_turns: int = Field(default=4, ge=1, le=20, description="Max turns for this agent (excluding sub-stages)")
    # Sub-stage specific limits
    max_chat_turns: int = Field(default=2, ge=1, le=10, description="Max turns in chat sub-stage")
    max_reflect_turns: int = Field(default=1, ge=1, le=5, description="Max turns in reflect sub-stage")


class InterviewConfig(BaseModel):
    """Global interview configuration.

    Controls the overall interview flow, which rounds are included,
    and how many turns each round gets.

    Example - Full interview (default):
        config = InterviewConfig()

    Example - Only tech rounds:
        config = InterviewConfig(
            rounds={
                "tech1": InterviewRoundConfig(enabled=True, max_turns=4),
                "tech2": InterviewRoundConfig(enabled=True, max_turns=4),
                "sysdes": InterviewRoundConfig(enabled=False),
                "leader": InterviewRoundConfig(enabled=False),
                "hr": InterviewRoundConfig(enabled=False)
            }
        )

    Example - Quick screening:
        config = InterviewConfig(
            total_max_turns=10,
            rounds={
                "tech1": InterviewRoundConfig(enabled=True, max_turns=3, max_chat_turns=1),
                "hr": InterviewRoundConfig(enabled=True, max_turns=2)
            }
        )
    """
    # Overall limit (safety net)
    total_max_turns: int = Field(default=30, ge=1, le=100, description="Global max turns across all rounds")

    # Per-round configuration
    rounds: Dict[str, InterviewRoundConfig] = Field(
        default_factory=lambda: {
            "tech1": InterviewRoundConfig(max_turns=4, max_chat_turns=2, max_reflect_turns=1),
            "tech2": InterviewRoundConfig(max_turns=4, max_chat_turns=2, max_reflect_turns=1),
            "sysdes": InterviewRoundConfig(max_turns=3, max_chat_turns=2, max_reflect_turns=1),
            "leader": InterviewRoundConfig(max_turns=2, max_chat_turns=1, max_reflect_turns=1),
            "hr": InterviewRoundConfig(max_turns=2, max_chat_turns=1, max_reflect_turns=1)
        }
    )

    # Order of rounds (can be customized)
    round_order: List[str] = Field(
        default_factory=lambda: ["tech1", "tech2", "sysdes", "leader", "hr"]
    )

    def get_enabled_rounds(self) -> List[str]:
        """Return list of enabled rounds in order."""
        return [r for r in self.round_order if self.rounds.get(r, InterviewRoundConfig()).enabled]

    def get_round_config(self, round_name: str) -> InterviewRoundConfig:
        """Get config for a specific round, with defaults."""
        return self.rounds.get(round_name, InterviewRoundConfig())


# ==================== Coding Interview Models ====================

class TestCase(BaseModel):
    """Single test case for coding problems."""
    input: str
    expected: str
    is_hidden: bool = False


class TestResult(BaseModel):
    """Result of executing a single test case."""
    case_id: int
    input_data: str
    expected: str
    actual: str
    passed: bool
    error_message: str = ""


class ExecutionResult(BaseModel):
    """Result of code execution with all test cases."""
    success: bool
    compile_output: str
    test_results: List[TestResult]
    overall_passed: bool
    execution_time_ms: float
    memory_usage_mb: float


class CodingProblem(BaseModel):
    """Represents a coding problem with test cases."""
    title: str
    description: str
    difficulty: str = Field(default="easy", pattern="^(easy|medium|hard)$")
    starter_code: str
    test_cases: List[TestCase]
    time_limit_sec: int = 2
    memory_limit_mb: int = 256


# ==================== Core Interview Models ====================

class CompetencyTag(BaseModel):
    dimension: Literal["coding", "system_design", "communication", "pressure_resistance", "culture_fit"]
    score: float = Field(..., ge=0.0, le=1.0)
    evidence: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class MemoryDistillate(BaseModel):
    candidate_profile: Dict[str, str]
    competency_vector: List[CompetencyTag]
    doubt_list: List[str]
    contradiction_alerts: List[str] = Field(default_factory=list)
    recommended_focus: str


class TransferPackage(BaseModel):
    session_id: str
    from_agent: str
    to_agent: str
    round_completed: int
    distillate: MemoryDistillate
    raw_digest: str
    budget_consumed: int
    challenge_flags: Optional[List[str]] = None
    agent_question: Optional[str] = None
    evaluation_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class BusinessContext(BaseModel):
    """JD 解析后存储的虚拟业务上下文"""
    domain: str
    team_size: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)
    core_challenges: List[str] = Field(default_factory=list)
    growth_stage: Optional[str] = None
    key_performance_metrics: List[str] = Field(default_factory=list)


class AgentOutput(BaseModel):
    """Agent 返回的标准化输出"""
    question: str
    evaluation_score: float = Field(..., ge=0.0, le=1.0)
    key_weaknesses: List[str] = Field(default_factory=list)
    follow_up_candidates: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None

    # Sub-stage management for Tech Agents
    sub_stage: Optional[str] = Field(default=None, description="Current sub-stage: chat/coding/reflect")

    # Coding-related fields
    coding_problem: Optional[CodingProblem] = Field(default=None, description="Coding problem for coding stage")
    code_execution_result: Optional[ExecutionResult] = Field(default=None, description="Result of code execution")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling nested models."""
        return self.model_dump()

