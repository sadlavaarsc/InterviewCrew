from interview_crew.state import InterviewState

_AGENTS = ["tech", "behavior", "project"]


def planner_node(state: InterviewState) -> dict:
    # 轮询分配：去掉 LLM 调用，避免 latency 瓶颈和 JSON 解析失败
    turn = state.get("turn", 1)
    idx = (turn - 1) % len(_AGENTS)
    return {"current_agent": _AGENTS[idx]}
