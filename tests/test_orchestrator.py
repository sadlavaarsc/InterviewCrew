import json
from interview_crew.state import InterviewState
from interview_crew.orchestrator.engine import Orchestrator
from interview_crew.orchestrator.jd_parser import JDParsingStrategy, BusinessContext


class FakeJDParser(JDParsingStrategy):
    def parse(self, jd_markdown: str) -> BusinessContext:
        return BusinessContext(domain="测试", tech_stack=["Python"])


_FAKE_AGENT_OUTPUT = json.dumps({
    "question": "请介绍一下你的项目经验。",
    "evaluation_score": 0.8,
    "key_weaknesses": ["缺乏分布式经验"],
    "follow_up_candidates": ["Redis 使用场景"],
    "reasoning": "测试",
})


def _fake_llm_invoke(messages, model_name=None, temperature=0.7):
    text = "\n".join(m.get("content", "") for m in messages)
    if "面试记录萃取助手" in text or "你从面试官角度分析" in text:
        return json.dumps({
            "candidate_profile": {"strong_area": "Python", "weak_area": "system_design"},
            "competency_vector": [
                {"dimension": "coding", "score": 0.8, "evidence": "3 years", "confidence": 0.9}
            ],
            "doubt_list": ["验证分布式"],
            "contradiction_alerts": [],
            "recommended_focus": "深入算法",
        })
    return _FAKE_AGENT_OUTPUT


def test_orchestrator_state_machine_transitions(monkeypatch):
    from interview_crew.llm.client import llm as llm_client
    monkeypatch.setattr(llm_client, "invoke", _fake_llm_invoke)

    state = InterviewState(session_id="test-001", max_turns=5)
    orch = Orchestrator(state, jd_parser=FakeJDParser())

    result = orch.step("你好")
    assert result.agent == "tech1"
    assert result.finished is False

    result = orch.step("回答1")
    assert result.agent == "tech2"

    result = orch.step("回答2")
    assert result.agent == "sysdes"

    result = orch.step("回答3")
    assert result.agent == "hr"

    result = orch.step("回答4")
    assert result.finished is True


def test_transfer_queue_grows(monkeypatch):
    from interview_crew.llm.client import llm as llm_client
    monkeypatch.setattr(llm_client, "invoke", _fake_llm_invoke)

    state = InterviewState(session_id="test-002", max_turns=3)
    orch = Orchestrator(state, jd_parser=FakeJDParser())

    orch.step("你好")
    assert len(state.transfer_queue) == 1

    orch.step("回答")
    assert len(state.transfer_queue) == 2


def test_conflict_flag_sets_on_divergence(monkeypatch):
    from interview_crew.llm.client import llm as llm_client
    monkeypatch.setattr(llm_client, "invoke", _fake_llm_invoke)

    state = InterviewState(session_id="test-003", max_turns=6)
    orch = Orchestrator(state, jd_parser=FakeJDParser())
    # Inject conflicting competency evaluations manually
    state.competency_history = [
        {"dimension": "coding", "score": 0.9, "turn": 1, "agent": "tech1"},
        {"dimension": "coding", "score": 0.3, "turn": 2, "agent": "tech2"},
    ]
    orch.step("回答")
    assert state.conflict_flag is True
