from interview_crew.graph import graph


def test_graph_compiles():
    assert graph is not None


def test_nodes_exist():
    nodes = list(graph.nodes.keys())
    for expected in ("aggregator", "planner", "tech", "behavior", "project"):
        assert expected in nodes


def test_start_node_exists():
    # 以节点存在性 + 编译通过作为基本验证
    assert "__start__" in graph.nodes
