from typing import Dict, Any, Callable
from interview_crew.config import settings


# Model tier aliases used across the system.
# - premium: stronger reasoning, used for technical interviews
# - default: cheaper / faster, used for report generation and downgrade paths
_DEFAULT_TIER = settings.default_model
_PREMIUM_TIER = settings.premium_model

_TOOL_POLICIES: Dict[str, Dict[str, Any]] = {
    "tech1": {
        "models": [_PREMIUM_TIER],
        "tools": ["rag_query", "code_judge", "code_generator", "code_executor"],
        "max_calls_per_round": 3,
        "enable_search": False,
        "budget": settings.budget_tech1,
    },
    "tech2": {
        "models": [_PREMIUM_TIER, _DEFAULT_TIER],
        "tools": ["rag_query", "deep_search", "counter_example_gen", "stress_trigger", "code_generator", "code_executor", "web_fetch"],
        "max_calls_per_round": 4,
        "enable_search": True,
        "budget": settings.budget_tech2,
    },
    "sysdes": {
        "models": [_PREMIUM_TIER, _DEFAULT_TIER],
        "tools": ["whiteboard_sim", "tradeoff_analyzer", "cross_ref_checker"],
        "max_calls_per_round": 3,
        "enable_search": True,
        "budget": settings.budget_sysdes,
    },
    "leader": {
        "models": [_PREMIUM_TIER],
        "tools": ["consistency_checker", "project_analyzer", "web_fetch"],
        "max_calls_per_round": 2,
        "enable_search": False,
        "budget": settings.budget_leader,
    },
    "hr": {
        "models": [_PREMIUM_TIER],
        "tools": ["consistency_checker", "red_flag_detector"],
        "max_calls_per_round": 2,
        "enable_search": False,
        "budget": settings.budget_hr,
    },
    "scribe": {
        "models": [_DEFAULT_TIER],
        "tools": [],
        "max_calls_per_round": 0,
        "enable_search": False,
        "budget": settings.budget_scribe,
    },
}


class ToolPolicy:
    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.permissions = _TOOL_POLICIES.get(agent_type, {
            "models": [_DEFAULT_TIER],
            "tools": [],
            "max_calls_per_round": 0,
            "enable_search": False,
            "budget": 0,
        })
        self.call_count = 0

    def check_permission(self, tool_name: str) -> bool:
        if self.call_count >= self.permissions["max_calls_per_round"]:
            return False
        return tool_name in self.permissions["tools"]

    def record_call(self) -> None:
        self.call_count += 1

    def get_budget(self) -> int:
        return self.permissions["budget"]

    def get_models(self) -> list:
        return self.permissions["models"]

    def downgrade_model(self) -> str:
        """Return the cheapest allowed model for this agent."""
        models = self.permissions["models"]
        if _DEFAULT_TIER in models:
            return _DEFAULT_TIER
        return models[-1] if models else _DEFAULT_TIER


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn

    def get(self, name: str) -> Callable:
        return self._tools[name]

    def list_tools(self) -> list:
        return list(self._tools.keys())


tool_registry = ToolRegistry()
