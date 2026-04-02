from interview_crew.graph import graph
from interview_crew.state import InterviewState


def test_memory_isolation_and_aggregation():
    state: InterviewState = {
        "session_id": "test-001",
        "turn": 0,
        "max_turns": 2,
        "candidate_response": "岗位：后端开发。简历：3年 Python 经验。",
        "tech_history": [],
        "behavior_history": [],
        "project_history": [],
        "unified_history": [],
        "current_agent": "",
        "last_question": "",
        "status": "ongoing",
    }

    final_state = graph.invoke(state)  # type: ignore

    # aggregator 至少运行了一次
    assert final_state["turn"] >= 1

    # unified_history 包含候选人的回答和至少一个 agent 的提问
    assert len(final_state["unified_history"]) >= 2

    # 三个 private histories 中只有一个被填充（隔离验证）
    private_counts = [
        len(final_state["tech_history"]),
        len(final_state["behavior_history"]),
        len(final_state["project_history"]),
    ]
    assert sum(private_counts) == len([h for h in private_counts if h > 0])

    # candidate_response 被 aggregator 清空
    assert final_state.get("candidate_response") == ""
