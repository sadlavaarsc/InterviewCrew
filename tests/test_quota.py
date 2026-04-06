"""Unit tests for TurnQuotaManager."""

import pytest
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from interview_crew.orchestrator.quota import (
    TurnQuotaManager,
    QuotaLevel,
    QuotaAction,
    QuotaCheckResult,
)
from interview_crew.protocol.schemas import (
    InterviewConfig,
    InterviewRoundConfig,
    StageTurnLimit,
)


@dataclass
class MockState:
    """Mock InterviewState for testing."""
    session_id: str = "test-session"
    turn: int = 0
    quota_consumed_agent: Dict[str, int] = field(default_factory=dict)
    quota_consumed_stage: Dict[str, Dict[str, int]] = field(default_factory=dict)
    round_turn_counts: Dict[str, int] = field(default_factory=dict)


def create_config(
    total_max_turns: int = 30,
    agent_max_turns: int = 6,
    stage_limits: Optional[list] = None
) -> InterviewConfig:
    """Helper to create test config."""
    if stage_limits is None:
        stage_limits = [
            StageTurnLimit(stage_name="chat", max_turns=2),
            StageTurnLimit(stage_name="coding", max_turns=5),
            StageTurnLimit(stage_name="reflect", max_turns=1),
        ]

    return InterviewConfig(
        total_max_turns=total_max_turns,
        rounds={
            "tech1": InterviewRoundConfig(
                enabled=True,
                max_turns=agent_max_turns,
                stage_turn_limits=stage_limits,
            ),
            "tech2": InterviewRoundConfig(
                enabled=True,
                max_turns=agent_max_turns,
                stage_turn_limits=stage_limits,
            ),
            "sysdes": InterviewRoundConfig(
                enabled=True,
                max_turns=4,
            ),
        }
    )


class TestQuotaInitialization:
    """Test QuotaManager initialization."""

    def test_init_from_config(self):
        """Test initialization from config."""
        config = create_config(total_max_turns=30, agent_max_turns=6)
        state = MockState()

        quota = TurnQuotaManager(config, state)

        # Check initial remaining quotas
        remaining = quota.get_remaining("tech1")
        assert remaining["global"] == 30
        assert remaining["agent"] == 6

    def test_init_from_state(self):
        """Test restoration from state with consumed quotas."""
        config = create_config(total_max_turns=30, agent_max_turns=6)
        state = MockState(
            turn=10,
            quota_consumed_agent={"tech1": 3, "tech2": 2},
            quota_consumed_stage={"tech1": {"chat": 2, "coding": 1}},
        )

        quota = TurnQuotaManager(config, state)

        # Check restored quotas
        remaining = quota.get_remaining("tech1")
        assert remaining["global"] == 20  # 30 - 10
        assert remaining["agent"] == 3    # 6 - 3

        remaining_stage = quota.get_remaining("tech1", "chat")
        assert remaining_stage["stage"] == 0  # 2 - 2

    def test_backward_compat_restore(self):
        """Test backward compatible restoration from round_turn_counts."""
        config = create_config(total_max_turns=30, agent_max_turns=10)
        state = MockState(
            turn=5,
            round_turn_counts={"tech1": 2},  # Old format
        )
        # No quota_consumed_agent

        quota = TurnQuotaManager(config, state)

        # New behavior: round_turn_counts is used directly as consumed count
        remaining = quota.get_remaining("tech1")
        assert remaining["global"] == 25  # 30 - 5
        # Agent remaining: 10 - 2 = 8 (direct mapping, not multiplied by 3)
        assert remaining["agent"] == 8


class TestQuotaCheck:
    """Test quota checking without consumption."""

    def test_check_all_available(self):
        """Test check when all quotas are available."""
        config = create_config()
        state = MockState()
        quota = TurnQuotaManager(config, state)

        result = quota.check("tech1", "chat")

        assert result.can_continue is True
        assert result.exhausted_level is None
        assert result.action == QuotaAction.CONTINUE

    def test_check_global_exhausted(self):
        """Test check when global quota is exhausted."""
        config = create_config(total_max_turns=5)
        state = MockState(turn=5)
        quota = TurnQuotaManager(config, state)

        result = quota.check("tech1", "chat")

        assert result.can_continue is False
        assert result.exhausted_level == QuotaLevel.GLOBAL
        assert result.action == QuotaAction.FINISH

    def test_check_agent_exhausted(self):
        """Test check when agent quota is exhausted."""
        config = create_config(agent_max_turns=3)
        state = MockState(quota_consumed_agent={"tech1": 3})
        quota = TurnQuotaManager(config, state)

        result = quota.check("tech1")

        assert result.can_continue is False
        assert result.exhausted_level == QuotaLevel.AGENT
        assert result.action == QuotaAction.SWITCH_AGENT

    def test_check_stage_exhausted(self):
        """Test check when sub-stage quota is exhausted."""
        config = create_config()
        state = MockState(
            quota_consumed_stage={"tech1": {"chat": 2}}
        )
        quota = TurnQuotaManager(config, state)

        result = quota.check("tech1", "chat")

        assert result.can_continue is False
        assert result.exhausted_level == QuotaLevel.STAGE
        assert result.action == QuotaAction.ADVANCE_STAGE


class TestQuotaConsume:
    """Test quota consumption."""

    def test_consume_decreases_all_levels(self):
        """Test that consume decreases all relevant quota levels."""
        config = create_config(total_max_turns=30, agent_max_turns=6)
        state = MockState()
        quota = TurnQuotaManager(config, state)

        # Consume one turn
        result = quota.consume("tech1", "chat")

        # Should be able to continue
        assert result.can_continue is True

        # Check all levels decreased
        remaining = quota.get_remaining("tech1", "chat")
        assert remaining["global"] == 29
        assert remaining["agent"] == 5
        assert remaining["stage"] == 1  # chat: 2 - 1

    def test_consume_persists_to_state(self):
        """Test that consume persists to state."""
        config = create_config()
        state = MockState()
        quota = TurnQuotaManager(config, state)

        quota.consume("tech1", "chat")

        # Check state was updated
        assert state.quota_consumed_agent.get("tech1") == 1
        assert state.quota_consumed_stage.get("tech1", {}).get("chat") == 1

    def test_consume_when_exhausted(self):
        """Test consume when quota is already exhausted."""
        config = create_config(agent_max_turns=1)
        state = MockState(quota_consumed_agent={"tech1": 1})
        quota = TurnQuotaManager(config, state)

        # Try to consume when already exhausted
        result = quota.consume("tech1")

        # Should report cannot continue
        assert result.can_continue is False
        assert result.action == QuotaAction.SWITCH_AGENT

        # But still consumes global quota
        remaining = quota.get_remaining("tech1")
        assert remaining["global"] == 29  # 30 - 1


class TestQuotaCheckAndConsume:
    """Test combined check and consume."""

    def test_check_and_consume_sequence(self):
        """Test sequence of check_and_consume calls."""
        # Use coding stage which has 5 turns (more than agent limit of 3)
        config = create_config(
            total_max_turns=10,
            agent_max_turns=3,
        )
        state = MockState()
        quota = TurnQuotaManager(config, state)

        # Consume 3 turns (should all succeed as coding has 5 turns)
        for i in range(3):
            result = quota.check_and_consume("tech1", "coding")
            assert result.can_continue is True

        # 4th turn should exhaust agent quota
        result = quota.check_and_consume("tech1", "coding")
        assert result.can_continue is False
        assert result.action == QuotaAction.SWITCH_AGENT


class TestStageLimits:
    """Test sub-stage limit handling."""

    def test_custom_stage_limits(self):
        """Test custom stage limits configuration."""
        stage_limits = [
            StageTurnLimit(stage_name="deep_dive", max_turns=3),
            StageTurnLimit(stage_name="coding", max_turns=5),
        ]
        config = create_config(stage_limits=stage_limits)
        state = MockState()
        quota = TurnQuotaManager(config, state)

        # Check deep_dive limit
        remaining = quota.get_remaining("tech1", "deep_dive")
        assert remaining["stage"] == 3

    def test_legacy_stage_fallback(self):
        """Test fallback to legacy stage limits."""
        # Config with only legacy limits
        config = InterviewConfig(
            rounds={
                "tech1": InterviewRoundConfig(
                    max_chat_turns=3,
                    max_coding_turns=8,
                    max_reflect_turns=2,
                )
            }
        )
        state = MockState()
        quota = TurnQuotaManager(config, state)

        # Should use legacy limits
        remaining = quota.get_remaining("tech1", "chat")
        assert remaining["stage"] == 3

        remaining = quota.get_remaining("tech1", "coding")
        assert remaining["stage"] == 8


class TestQuotaReset:
    """Test quota reset functionality."""

    def test_reset_stage_quota(self):
        """Test resetting stage quota for new round."""
        config = create_config()
        state = MockState(
            quota_consumed_stage={"tech1": {"chat": 2}}
        )
        quota = TurnQuotaManager(config, state)

        # Chat should be exhausted
        remaining = quota.get_remaining("tech1", "chat")
        assert remaining["stage"] == 0

        # Reset chat quota
        quota.reset_stage_quota("tech1", "chat")

        # Should be full again
        remaining = quota.get_remaining("tech1", "chat")
        assert remaining["stage"] == 2


class TestQuotaGetConsumed:
    """Test get_consumed method."""

    def test_get_consumed(self):
        """Test getting consumed quotas."""
        config = create_config(total_max_turns=30, agent_max_turns=6)
        state = MockState(turn=5)
        quota = TurnQuotaManager(config, state)

        # Consume some quotas
        quota.consume("tech1", "chat")
        quota.consume("tech1", "chat")

        consumed = quota.get_consumed("tech1", "chat")
        assert consumed["global"] == 7  # 5 + 2
        assert consumed["agent"] == 2
        assert consumed["stage"] == 2


class TestEdgeCases:
    """Test edge cases."""

    def test_non_tech_agent_no_stage(self):
        """Test non-tech agent without sub-stage."""
        config = create_config()
        state = MockState()
        quota = TurnQuotaManager(config, state)

        # Sysdes has no sub-stage
        result = quota.check("sysdes")
        assert result.can_continue is True

        # Should not have stage level
        remaining = quota.get_remaining("sysdes")
        assert "stage" not in remaining

    def test_multiple_agents_independent(self):
        """Test that agents have independent quotas."""
        config = create_config(agent_max_turns=3)
        state = MockState(
            quota_consumed_agent={"tech1": 3}  # tech1 exhausted
        )
        quota = TurnQuotaManager(config, state)

        # tech1 should be exhausted
        result = quota.check("tech1")
        assert result.can_continue is False

        # tech2 should still have quota
        result = quota.check("tech2")
        assert result.can_continue is True
        remaining = quota.get_remaining("tech2")
        assert remaining["agent"] == 3

    def test_zero_turn_state(self):
        """Test with zero turn state."""
        config = create_config()
        state = MockState(turn=0)
        quota = TurnQuotaManager(config, state)

        remaining = quota.get_remaining("tech1")
        assert remaining["global"] == 30

    def test_invalid_agent(self):
        """Test with unknown agent."""
        config = create_config()
        state = MockState()
        quota = TurnQuotaManager(config, state)

        # Should use default limits
        result = quota.check("unknown_agent")
        assert result.can_continue is True
        remaining = quota.get_remaining("unknown_agent")
        assert remaining["agent"] == 6  # Default max_turns
