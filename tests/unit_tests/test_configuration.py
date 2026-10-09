from langgraph.pregel import Pregel

from agent.graph import Context, builder, graph


def test_graph_compiles() -> None:
    """Graph compiles into a valid Pregel instance."""
    assert isinstance(graph, Pregel)


def test_graph_compiles_with_checkpointer(graph) -> None:
    """Graph compiles with a checkpointer and store (used by LangGraph Platform)."""
    assert isinstance(graph, Pregel)


def test_graph_has_default_agent_node() -> None:
    """Graph has a single default_agent entry node."""
    assert list(builder.nodes.keys()) == ["default_agent"]


def test_context_schema_has_model_param() -> None:
    """Context schema defines the default-agent model."""
    assert "default_model" in Context.__annotations__
