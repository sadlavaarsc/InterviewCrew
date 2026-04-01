import json
import random
from pathlib import Path
from interview_crew.state import InterviewState, Message
from interview_crew.llm.client import llm

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planner.txt"
_PLANNER_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def planner_node(state: InterviewState) -> dict:
    messages: list[Message] = [{"role": "system", "content": _PLANNER_PROMPT}]
    if state.get("unified_history"):
        messages.extend(state["unified_history"])
    if state.get("candidate_response"):
        messages.append({"role": "user", "content": f"候选人最新回答：{state['candidate_response']}"})

    try:
        raw = llm.invoke(messages)
        data = json.loads(raw.strip())
        next_agent = data.get("next_agent", "")
        if next_agent not in ("tech", "behavior", "project"):
            raise ValueError(f"Invalid next_agent: {next_agent}")
    except Exception as e:
        print(f"[Planner] JSON parse failed: {e}, fallback to random.")
        next_agent = random.choice(["tech", "behavior", "project"])

    return {"current_agent": next_agent}
