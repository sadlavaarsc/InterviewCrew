from typing import TypedDict, List, Annotated
import operator

Message = dict  # {"role": str, "content": str}


class InterviewState(TypedDict):
    session_id: str
    turn: int
    max_turns: int

    candidate_response: str

    tech_history: Annotated[List[Message], operator.add]
    behavior_history: Annotated[List[Message], operator.add]
    project_history: Annotated[List[Message], operator.add]

    unified_history: Annotated[List[Message], operator.add]
    current_agent: str          # "tech" | "behavior" | "project"
    last_question: str
    status: str                 # "ongoing" | "finished"
