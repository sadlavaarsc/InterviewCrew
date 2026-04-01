from langgraph.graph import StateGraph, END, START
from interview_crew.state import InterviewState
from interview_crew.nodes.aggregator import aggregator_node
from interview_crew.nodes.planner import planner_node
from interview_crew.nodes.tech_agent import tech_agent_node
from interview_crew.nodes.behavior_agent import behavior_agent_node
from interview_crew.nodes.project_agent import project_agent_node


def router(state: InterviewState) -> str:
    return state["current_agent"]


def should_finish(state: InterviewState) -> str:
    if state.get("status") == "finished" or state.get("turn", 0) >= state.get("max_turns", 6):
        return END
    return "planner"


workflow = StateGraph(InterviewState)

workflow.add_node("aggregator", aggregator_node)
workflow.add_node("planner", planner_node)
workflow.add_node("tech", tech_agent_node)
workflow.add_node("behavior", behavior_agent_node)
workflow.add_node("project", project_agent_node)

workflow.add_edge(START, "aggregator")
workflow.add_conditional_edges("aggregator", should_finish, {END: END, "planner": "planner"})
workflow.add_conditional_edges(
    "planner",
    router,
    {"tech": "tech", "behavior": "behavior", "project": "project"},
)
workflow.add_edge("tech", "aggregator")
workflow.add_edge("behavior", "aggregator")
workflow.add_edge("project", "aggregator")

graph = workflow.compile()
