from interview_crew.state import InterviewState, Message


def project_agent_node(state: InterviewState) -> dict:
    question = "[Project Stub] 请详细介绍你上一个项目的技术选型和量化收益。"
    assistant_msg: Message = {"role": "assistant", "name": "ProjectAgent", "content": question}
    return {
        "project_history": [assistant_msg],
        "unified_history": [assistant_msg],
        "last_question": question,
    }
