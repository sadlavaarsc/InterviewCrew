from interview_crew.state import InterviewState, Message


def behavior_agent_node(state: InterviewState) -> dict:
    question = "[Behavior Stub] 你觉得自己最大的软技能短板是什么？"
    assistant_msg: Message = {"role": "assistant", "name": "BehaviorAgent", "content": question}
    return {
        "behavior_history": [assistant_msg],
        "unified_history": [assistant_msg],
        "last_question": question,
    }
