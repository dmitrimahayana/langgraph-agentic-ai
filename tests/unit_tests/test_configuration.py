from langgraph.pregel import Pregel

from agent.graph import builder, graph, Context


def test_graph_compiles() -> None:
    """Graph compiles into a valid Pregel instance."""
    assert isinstance(graph, Pregel)


def test_graph_compiles_with_checkpointer(graph) -> None:
    """Graph compiles with a checkpointer (used by LangGraph Platform)."""
    assert isinstance(graph, Pregel)


def test_graph_has_expected_nodes() -> None:
    """Graph contains the call_agent_with_tools node."""
    node_names = list(builder.nodes.keys())
    assert "call_agent_with_tools" in node_names


def test_context_schema_has_configurable_param() -> None:
    """Context schema defines my_configurable_param."""
    assert "my_configurable_param" in Context.__annotations__
