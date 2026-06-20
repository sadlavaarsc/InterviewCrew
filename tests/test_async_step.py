"""Tests for the async streaming step path in Orchestrator.

Uses asyncio.run() directly so pytest-asyncio is not required.
"""

import json
import asyncio

from interview_crew.orchestrator.engine import Orchestrator
from interview_crew.state import InterviewState
from interview_crew.protocol.schemas import InterviewConfig, MemoryDistillate, CompetencyTag


_FAKE_STREAM_CHUNKS = [
    '{"question": "请',
    '介绍',
    '一下",',
    '"evaluation_score": 0.8,',
    '"key_weaknesses": [],',
    '"follow_up_candidates": [],',
    '"reasoning": "test"}',
]

_FAKE_STREAM_FULL = "".join(_FAKE_STREAM_CHUNKS)


def _make_orchestrator() -> Orchestrator:
    state = InterviewState(
        session_id="async-test-001",
        config=InterviewConfig(),
        resume_text="Python backend engineer",
        jd_text="后端工程师",
    )
    return Orchestrator(state)


def _fake_distillate(*args, **kwargs):
    return MemoryDistillate(
        candidate_profile={},
        competency_vector=[],
        doubt_list=[],
        contradiction_alerts=[],
        recommended_focus="",
    )


def _fake_distillate_with_competency(*args, **kwargs):
    return MemoryDistillate(
        candidate_profile={},
        competency_vector=[
            CompetencyTag(dimension="coding", score=0.8, evidence="", confidence=0.8)
        ],
        doubt_list=[],
        contradiction_alerts=[],
        recommended_focus="",
    )


def test_async_step_yields_intermediate_and_final_results(monkeypatch):
    """async_step should yield partial StepResults while streaming and a final one."""
    orch = _make_orchestrator()

    monkeypatch.setattr("interview_crew.orchestrator.engine.distill_memory", _fake_distillate)

    async def fake_astream(*args, **kwargs):
        for chunk in _FAKE_STREAM_CHUNKS:
            yield chunk

    monkeypatch.setattr("interview_crew.orchestrator.engine.async_llm.astream", fake_astream)

    async def collect():
        results = []
        async for result in orch.async_step("你好"):
            results.append(result)
        return results

    results = asyncio.run(collect())

    assert len(results) > 1

    for r in results[:-1]:
        assert r.finished is False
        assert r.agent == "tech1"
        assert len(r.question) > 0

    final = results[-1]
    assert final.agent == "tech1"
    assert final.question == json.loads(_FAKE_STREAM_FULL)["question"]
    assert final.finished is False


def test_async_step_uses_async_llm(monkeypatch):
    """async_step should call async_llm.astream, not the synchronous client."""
    orch = _make_orchestrator()

    monkeypatch.setattr("interview_crew.orchestrator.engine.distill_memory", _fake_distillate)

    called = {"count": 0}

    async def fake_astream(*args, **kwargs):
        called["count"] += 1
        yield '{"question": "Q", "evaluation_score": 0.5}'

    monkeypatch.setattr("interview_crew.orchestrator.engine.async_llm.astream", fake_astream)

    async def consume():
        async for _ in orch.async_step("hello"):
            pass

    asyncio.run(consume())

    assert called["count"] == 1


def test_async_step_does_not_break_existing_state(monkeypatch):
    """Running async_step should update state similarly to sync step."""
    orch = _make_orchestrator()

    monkeypatch.setattr(
        "interview_crew.orchestrator.engine.distill_memory",
        _fake_distillate_with_competency,
    )

    async def fake_astream(*args, **kwargs):
        yield '{"question": "Q1", "evaluation_score": 0.8}'

    monkeypatch.setattr("interview_crew.orchestrator.engine.async_llm.astream", fake_astream)

    async def consume():
        async for _ in orch.async_step("hello"):
            pass

    asyncio.run(consume())

    assert orch.state.turn == 1
    assert orch.state.current_agent == "tech1"
    assert len(orch.state.unified_history) == 2
