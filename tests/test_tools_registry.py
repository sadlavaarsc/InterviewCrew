from interview_crew.tools.registry import ToolPolicy


def test_tech1_permissions():
    policy = ToolPolicy("tech1")
    assert policy.check_permission("rag_query") is True
    assert policy.check_permission("code_judge") is True
    assert policy.check_permission("deep_search") is False
    assert policy.check_permission("whiteboard_sim") is False


def test_tech2_permissions():
    policy = ToolPolicy("tech2")
    assert policy.check_permission("deep_search") is True
    assert policy.check_permission("counter_example_gen") is True
    assert policy.check_permission("whiteboard_sim") is False


def test_max_calls_enforced():
    policy = ToolPolicy("tech1")
    assert policy.permissions["max_calls_per_round"] == 2
    policy.record_call()
    assert policy.check_permission("rag_query") is True
    policy.record_call()
    assert policy.check_permission("rag_query") is False


def test_downgrade_model():
    policy = ToolPolicy("scribe")
    assert policy.downgrade_model() == "qwen3.5-flash"
