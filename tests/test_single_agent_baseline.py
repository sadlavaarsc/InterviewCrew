"""Tests for Single Agent Baseline."""

import pytest
from unittest.mock import patch, MagicMock

from interview_crew.baseline.single_agent_orchestrator import SingleAgentOrchestrator, StepResult
from interview_crew.baseline.single_agent import SingleInterviewAgent
from interview_crew.state import InterviewState
from interview_crew.protocol.schemas import InterviewConfig, MemoryDistillate


class TestSingleAgentOrchestrator:
    """Test Single Agent Orchestrator."""

    def test_orchestrator_initialization(self):
        """Test orchestrator can be initialized."""
        state = InterviewState(
            session_id="test-session",
            config=InterviewConfig(total_max_turns=5)
        )
        orchestrator = SingleAgentOrchestrator(state)

        assert orchestrator.state == state
        assert orchestrator.turn_count == 0
        assert orchestrator.llm_call_count == 0
        assert orchestrator.token_consumed == 0

    def test_step_result_structure(self):
        """Test StepResult has the expected structure with detailed token stats."""
        result = StepResult(
            agent="interviewer",
            question="Test question",
            finished=False,
            report="",
            token_consumed_this_turn=100,
            total_token_consumed=500,
            plus_token_consumed_this_turn=80,
            flash_token_consumed_this_turn=20,
            total_plus_token_consumed=400,
            total_flash_token_consumed=100
        )

        assert result.agent == "interviewer"
        assert result.question == "Test question"
        assert result.finished is False
        assert result.token_consumed_this_turn == 100
        assert result.total_token_consumed == 500
        # Detailed breakdown
        assert result.plus_token_consumed_this_turn == 80
        assert result.flash_token_consumed_this_turn == 20
        assert result.total_plus_token_consumed == 400
        assert result.total_flash_token_consumed == 100

    def test_get_stats(self):
        """Test get_stats returns expected structure with detailed breakdown."""
        state = InterviewState(
            session_id="test-session",
            config=InterviewConfig(total_max_turns=5)
        )
        orchestrator = SingleAgentOrchestrator(state)

        stats = orchestrator.get_stats()

        assert "turn_count" in stats
        assert "llm_call_count" in stats
        assert "token_consumed" in stats
        assert "mode" in stats
        assert stats["mode"] == "single_agent"
        # Detailed breakdown by model tier
        assert "plus_call_count" in stats
        assert "flash_call_count" in stats
        assert "total_plus_token_consumed" in stats
        assert "total_flash_token_consumed" in stats

    @patch('interview_crew.baseline.single_agent_orchestrator.llm.invoke')
    def test_step_with_mock_llm(self, mock_invoke):
        """Test step method with mocked LLM - now returns stage name like MAS."""
        mock_invoke.return_value = "Test question from LLM"

        state = InterviewState(
            session_id="test-session",
            config=InterviewConfig(total_max_turns=5)
        )
        orchestrator = SingleAgentOrchestrator(state)

        result = orchestrator.step("Hello, I'm a candidate")

        # Now returns current stage (tech1) instead of fixed "interviewer"
        assert result.agent == "tech1"  # First stage
        assert result.question == "Test question from LLM"
        assert result.finished is False
        assert orchestrator.turn_count == 1
        assert orchestrator.current_stage_index == 0  # Still in first stage

    @patch('interview_crew.baseline.single_agent_orchestrator.llm.invoke')
    def test_interview_finishes_after_max_turns(self, mock_invoke):
        """Test interview finishes after max turns."""
        mock_invoke.return_value = "Final report"

        state = InterviewState(
            session_id="test-session",
            config=InterviewConfig(total_max_turns=2)
        )
        orchestrator = SingleAgentOrchestrator(state)

        # First turn
        result1 = orchestrator.step("Hello")
        assert result1.finished is False

        # Second turn (should finish)
        result2 = orchestrator.step("Answer")
        assert result2.finished is True
        assert result2.report != ""  # Should have report


class TestSingleInterviewAgent:
    """Test Single Interview Agent."""

    def test_agent_initialization(self):
        """Test agent can be initialized."""
        agent = SingleInterviewAgent()

        assert agent.name == "single_interviewer"
        assert agent.preferred_model == "qwen3.5-plus"

    def test_build_context_with_empty_distillate(self):
        """Test build_context with empty distillate."""
        agent = SingleInterviewAgent()
        distillate = MemoryDistillate(
            candidate_profile={},
            competency_vector=[],
            doubt_list=[],
            recommended_focus=""
        )

        context = agent.build_context(distillate)

        assert isinstance(context, str)
        assert "暂无需特别关注的记忆摘要" in context

    def test_build_context_with_data(self):
        """Test build_context with data."""
        from interview_crew.protocol.schemas import CompetencyTag

        agent = SingleInterviewAgent()
        distillate = MemoryDistillate(
            candidate_profile={"strength": "Python expert"},
            competency_vector=[
                CompetencyTag(
                    dimension="coding",
                    score=0.8,
                    evidence="Good coding skills",
                    confidence=0.9
                )
            ],
            doubt_list=["Need to verify system design skills"],
            recommended_focus="Ask about distributed systems"
        )

        context = agent.build_context(distillate)

        assert "coding" in context
        assert "0.80" in context  # Formatted score
        assert "Need to verify system design skills" in context

    def test_parse_simple_with_json(self):
        """Test _parse_simple with valid JSON."""
        agent = SingleInterviewAgent()
        raw = '{"question": "Test question", "evaluation_score": 0.8, "key_weaknesses": ["a"], "follow_up_candidates": ["b"], "reasoning": "test"}'

        output = agent._parse_simple(raw)

        assert output.question == "Test question"
        assert output.evaluation_score == 0.8
        assert output.key_weaknesses == ["a"]

    def test_parse_simple_with_invalid_json(self):
        """Test _parse_simple falls back to raw text."""
        agent = SingleInterviewAgent()
        raw = "This is not JSON"

        output = agent._parse_simple(raw)

        assert output.question == "This is not JSON"
        assert output.evaluation_score == 0.5  # Default
        assert "parse failed" in output.reasoning


class TestBaselineIntegration:
    """Integration tests for baseline."""

    @patch('interview_crew.baseline.single_agent_orchestrator.llm.invoke')
    def test_full_interview_flow(self, mock_invoke):
        """Test a full interview flow with single agent."""
        mock_invoke.return_value = "Interview question"

        state = InterviewState(
            session_id="integration-test",
            config=InterviewConfig(total_max_turns=3)
        )
        orchestrator = SingleAgentOrchestrator(state)

        # Simulate a 3-turn interview
        responses = ["Answer 1", "Answer 2", "Answer 3"]

        for i, response in enumerate(responses):
            result = orchestrator.step(response)

            if i < 2:
                assert result.finished is False
            else:
                assert result.finished is True

        assert orchestrator.turn_count == 3
        # llm_call_count may be less than 3 because final report generation uses different logic
        assert orchestrator.llm_call_count >= 2
        assert len(state.unified_history) > 0

    def test_stage_progression(self):
        """Test that stages progress in MAS order: tech1 -> tech2 -> sysdes -> leader -> hr"""
        state = InterviewState(
            session_id="test-stage-progression",
            config=InterviewConfig(total_max_turns=20)
        )
        orchestrator = SingleAgentOrchestrator(state)

        # Check initial stage
        assert orchestrator._get_current_stage() == "tech1"
        assert orchestrator.STAGES == ["tech1", "tech2", "sysdes", "leader", "hr"]

        # Simulate advancing through stages
        orchestrator.current_stage_index = 1
        assert orchestrator._get_current_stage() == "tech2"

        orchestrator.current_stage_index = 4
        assert orchestrator._get_current_stage() == "hr"

    def test_stage_config(self):
        """Test stage configuration matches MAS defaults."""
        state = InterviewState(
            session_id="test-config",
            config=InterviewConfig(total_max_turns=10)
        )
        orchestrator = SingleAgentOrchestrator(state)

        # Check default stage configs match MAS
        assert orchestrator._get_stage_config("tech1")["max_turns"] == 4
        assert orchestrator._get_stage_config("tech2")["max_turns"] == 4
        assert orchestrator._get_stage_config("sysdes")["max_turns"] == 3
        assert orchestrator._get_stage_config("leader")["max_turns"] == 2
        assert orchestrator._get_stage_config("hr")["max_turns"] == 2

    def test_mode_identification(self):
        """Test that orchestrator identifies as single_agent mode."""
        state = InterviewState(
            session_id="test",
            config=InterviewConfig(total_max_turns=5)
        )
        orchestrator = SingleAgentOrchestrator(state)

        stats = orchestrator.get_stats()
        assert stats["mode"] == "single_agent"
