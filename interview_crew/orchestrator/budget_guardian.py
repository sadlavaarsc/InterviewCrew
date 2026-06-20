from interview_crew.config import settings
from interview_crew.llm.model_resolver import get_default_model, get_premium_model


class BudgetGuardian:
    def __init__(self):
        self.total_consumed = 0

    def check_and_downgrade(self, agent_name: str, estimated_tokens: int) -> str:
        """Return the model name to use; downgrade if estimated tokens exceed budget."""
        budget = self._get_budget(agent_name)
        if estimated_tokens > budget:
            return get_default_model()
        return get_premium_model()

    def _get_budget(self, agent_name: str) -> int:
        budgets = {
            "tech1": settings.budget_tech1,
            "tech2": settings.budget_tech2,
            "sysdes": settings.budget_sysdes,
            "hr": settings.budget_hr,
            "scribe": settings.budget_scribe,
        }
        return budgets.get(agent_name, 999999)

    def consume(self, tokens: int) -> None:
        self.total_consumed += tokens
