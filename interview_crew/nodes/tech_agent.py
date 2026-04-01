from pathlib import Path
from interview_crew.state import InterviewState, Message
from interview_crew.llm.client import llm
from interview_crew.memory.isolated import build_agent_messages

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "tech.txt"
_TECH_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def tech_agent_node(state: InterviewState) -> dict:
    messages = build_agent_messages(
        state.get("tech_history", []),
        _TECH_PROMPT,
        state.get("candidate_response", ""),
    )
    content = llm.invoke(messages)
    assistant_msg: Message = {"role": "assistant", "name": "TechAgent", "content": content}
    return {
        "tech_history": [assistant_msg],
        "unified_history": [assistant_msg],
        "last_question": content,
    }
