from pathlib import Path
from interview_crew.state import InterviewState, Message
from interview_crew.llm.client import llm
from interview_crew.memory.isolated import build_agent_messages

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "project.txt"
_PROJECT_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def project_agent_node(state: InterviewState) -> dict:
    messages = build_agent_messages(
        state.get("project_history", []),
        _PROJECT_PROMPT,
        state.get("candidate_response", ""),
    )
    content = llm.invoke(messages)
    assistant_msg: Message = {"role": "assistant", "name": "ProjectAgent", "content": content}
    return {
        "project_history": [assistant_msg],
        "unified_history": [assistant_msg],
        "last_question": content,
    }
