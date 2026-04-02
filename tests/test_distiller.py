import json
from interview_crew.memory.distiller import distill_memory

_FAKE_DISTILL_OUTPUT = json.dumps({
    "candidate_profile": {"strong_area": "Python", "weak_area": "system_design"},
    "competency_vector": [
        {"dimension": "coding", "score": 0.8, "evidence": "3 years exp", "confidence": 0.9}
    ],
    "doubt_list": ["需要验证分布式经验"],
    "contradiction_alerts": [],
    "recommended_focus": "深入算法细节",
})


def test_distill_memory_returns_valid_structure(monkeypatch):
    from interview_crew.memory import distiller as distiller_mod
    monkeypatch.setattr(distiller_mod.llm, "invoke", lambda *args, **kwargs: _FAKE_DISTILL_OUTPUT)

    dialogue = [
        {"role": "user", "content": "岗位：后端开发"},
        {"role": "assistant", "content": "请介绍一下你的项目经验"},
        {"role": "user", "content": "我做了3年Python"},
    ]
    result = distill_memory(dialogue, session_id="test", turn=1)
    assert result is not None
    assert hasattr(result, "candidate_profile")
    assert hasattr(result, "competency_vector")
    assert hasattr(result, "doubt_list")
    assert hasattr(result, "recommended_focus")
    assert result.recommended_focus == "深入算法细节"
