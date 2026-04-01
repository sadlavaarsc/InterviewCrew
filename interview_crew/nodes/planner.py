import random
from interview_crew.state import InterviewState


def planner_node(state: InterviewState) -> dict:
    # stub: random choice among agents
    return {"current_agent": random.choice(["tech", "behavior", "project"])}
