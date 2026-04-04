from interview_crew.tools.registry import ToolPolicy, tool_registry
from interview_crew.tools.stubs import (
    rag_query,
    code_judge,
    deep_search,
    counter_example_gen,
    stress_trigger,
    whiteboard_sim,
    tradeoff_analyzer,
    cross_ref_checker,
    consistency_checker,
    red_flag_detector,
    web_fetch,
)

# Register all tools to the global registry
tool_registry.register("rag_query", rag_query)
tool_registry.register("code_judge", code_judge)
tool_registry.register("deep_search", deep_search)
tool_registry.register("counter_example_gen", counter_example_gen)
tool_registry.register("stress_trigger", stress_trigger)
tool_registry.register("whiteboard_sim", whiteboard_sim)
tool_registry.register("tradeoff_analyzer", tradeoff_analyzer)
tool_registry.register("cross_ref_checker", cross_ref_checker)
tool_registry.register("consistency_checker", consistency_checker)
tool_registry.register("red_flag_detector", red_flag_detector)
tool_registry.register("web_fetch", web_fetch)

__all__ = [
    "ToolPolicy",
    "tool_registry",
    "rag_query",
    "code_judge",
    "deep_search",
    "counter_example_gen",
    "stress_trigger",
    "whiteboard_sim",
    "tradeoff_analyzer",
    "cross_ref_checker",
    "consistency_checker",
    "red_flag_detector",
    "web_fetch",
]
