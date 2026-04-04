"""Single Agent Baseline for InterviewCrew.

提供与 Multi-Agent 版本相同的接口，用于对比测试。
"""

from .single_agent_orchestrator import SingleAgentOrchestrator
from .single_agent import SingleInterviewAgent

__all__ = ["SingleAgentOrchestrator", "SingleInterviewAgent"]
