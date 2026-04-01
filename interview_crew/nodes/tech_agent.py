from interview_crew.state import InterviewState, Message


def tech_agent_node(state: InterviewState) -> dict:
    question = "[Tech Stub] 请简述一下你最熟悉的数据结构及其时间复杂度。"
    assistant_msg: Message = {"role": "assistant", "name": "TechAgent", "content": question}
    return {
        "tech_history": [assistant_msg],
        "unified_history": [assistant_msg],
        "last_question": question,
    }
