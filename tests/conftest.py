import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.graph import builder


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio to use asyncio backend for async tests."""
    return "asyncio"


@pytest.fixture
def graph():
    """
    Compile graph with in-memory checkpointer for testing.

    This fixture provides a fresh graph instance with memory-based
    checkpointing for each test, ensuring test isolation.
    """
    return builder.compile(checkpointer=MemorySaver())
