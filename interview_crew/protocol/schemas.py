from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Dict


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
