from interview_crew.state import InterviewState, Message


def aggregator_node(state: InterviewState) -> dict:
    updates: dict = {"turn": state.get("turn", 0) + 1}

    if state.get("candidate_response"):
        user_msg: Message = {"role": "user", "content": state["candidate_response"]}
        updates["unified_history"] = [user_msg]
        # 清空避免重复加入
        updates["candidate_response"] = ""

    if updates["turn"] >= state.get("max_turns", 6):
        updates["status"] = "finished"
    else:
        updates["status"] = "ongoing"

    return updates
