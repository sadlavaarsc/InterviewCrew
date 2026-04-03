import json

from fastapi.testclient import TestClient

from interview_crew.api import app
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


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_get_session(monkeypatch):
    from interview_crew.llm.client import llm as llm_client
    monkeypatch.setattr(llm_client, "invoke", _fake_llm_invoke)

    client = TestClient(app)
    response = client.post("/sessions", json={
        "max_turns": 4,
        "candidate_response": "岗位：后端。简历：3年Python。",
    })
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "ongoing"
    session_id = data["session_id"]

    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    state = response.json()
    assert state["session_id"] == session_id
    assert state["max_turns"] == 4
    assert state["status"] == "ongoing"


def test_step_endpoint(monkeypatch):
    from interview_crew.llm.client import llm as llm_client
    monkeypatch.setattr(llm_client, "invoke", _fake_llm_invoke)

    client = TestClient(app)
    response = client.post("/sessions", json={
        "max_turns": 5,
        "candidate_response": "你好",
    })
    session_id = response.json()["session_id"]

    result = client.post(f"/sessions/{session_id}/step", json={"candidate_response": "你好"})
    assert result.status_code == 200
    data = result.json()
    assert data["agent"] == "tech1"
    assert data["finished"] is False
    assert "question" in data


def test_step_until_finished(monkeypatch):
    from interview_crew.llm.client import llm as llm_client
    monkeypatch.setattr(llm_client, "invoke", _fake_llm_invoke)

    client = TestClient(app)
    response = client.post("/sessions", json={
        "max_turns": 2,
        "candidate_response": "开始",
    })
    session_id = response.json()["session_id"]

    # step 1
    r1 = client.post(f"/sessions/{session_id}/step", json={"candidate_response": "回答1"})
    assert r1.json()["finished"] is False

    # step 2 (should reach max_turns and finish)
    r2 = client.post(f"/sessions/{session_id}/step", json={"candidate_response": "回答2"})
    assert r2.json()["finished"] is True


def test_session_not_found():
    client = TestClient(app)
    response = client.get("/sessions/nonexistent")
    assert response.status_code == 404

    response = client.post("/sessions/nonexistent/step", json={"candidate_response": "hello"})
    assert response.status_code == 404
