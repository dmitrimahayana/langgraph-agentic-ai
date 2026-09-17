from langgraph.pregel import Pregel

from agent.graph import builder, graph, Context


def test_graph_compiles() -> None:
    """Graph compiles into a valid Pregel instance."""
    assert isinstance(graph, Pregel)


def test_graph_compiles_with_checkpointer(graph) -> None:
    """Graph compiles with a checkpointer (used by LangGraph Platform)."""
    assert isinstance(graph, Pregel)


def test_graph_has_expected_nodes() -> None:
    """Graph contains expected agent nodes."""
    node_names = list(builder.nodes.keys())
    # Verify all required nodes exist
    assert "orchestrator" in node_names
    assert "classifier" in node_names
    assert "researcher" in node_names
    assert "coder" in node_names


def test_context_schema_has_model_params() -> None:
    """Context schema defines model configuration parameters."""
    assert "orchestrator_model" in Context.__annotations__
    assert "researcher_model" in Context.__annotations__
    assert "coder_model" in Context.__annotations__
