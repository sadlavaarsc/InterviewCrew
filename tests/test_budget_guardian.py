from interview_crew.orchestrator.budget_guardian import BudgetGuardian
from interview_crew.config import settings


def test_budget_guardian_downgrades_when_over_budget():
    bg = BudgetGuardian()
    model = bg.check_and_downgrade("tech1", 99999)
    assert model == settings.qwen_flash_model


def test_budget_guardian_uses_plus_when_under_budget():
    bg = BudgetGuardian()
    model = bg.check_and_downgrade("tech1", 10)
    assert model == settings.qwen_plus_model


def test_budget_guardian_tracks_consumption():
    bg = BudgetGuardian()
    bg.consume(100)
    assert bg.total_consumed == 100
