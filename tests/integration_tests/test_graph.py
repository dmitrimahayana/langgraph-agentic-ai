import pytest

pytestmark = pytest.mark.anyio


async def test_agent_responds(graph) -> None:
    """Test that the agent can respond to a simple message."""
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Hello, what can you do?"}]},
        config={"configurable": {"thread_id": "test-thread-basic"}},
    )
    assert result["messages"]
    # Last message should be from the assistant
    assert result["messages"][-1].type == "ai"


async def test_agent_remembers_name_in_thread(graph) -> None:
    """Test that the agent remembers context within the same thread (conversation)."""
    config = {"configurable": {"thread_id": "test-thread-memory"}}

    # First turn: tell the agent your name
    result1 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "My name is Dmitri."}]},
        config=config,
    )
    assert result1["messages"]
    assert result1["messages"][-1].type == "ai"

    # Second turn: ask the agent your name (same thread)
    result2 = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "What is my name?"}]},
        config=config,
    )
    assert result2["messages"]
    last_msg = result2["messages"][-1].content.lower()
    assert "dmitri" in last_msg, f"Expected 'dmitri' in response, got: {last_msg}"


async def test_separate_threads_no_crosstalk(graph) -> None:
    """Test that different threads don't share memory."""
    config_a = {"configurable": {"thread_id": "thread-user-a"}}
    config_b = {"configurable": {"thread_id": "thread-user-b"}}

    # User A says their name
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "My name is Alice."}]},
        config=config_a,
    )

    # User B asks "what is my name?" — should NOT know Alice
    result_b = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "What is my name?"}]},
        config=config_b,
    )
    last_msg = result_b["messages"][-1].content.lower()
    assert "alice" not in last_msg, (
        f"Thread B should not know about Alice, got: {last_msg}"
    )
