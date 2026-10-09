import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from agent.graph import builder


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio to use asyncio backend for async tests."""
    return "asyncio"


@pytest.fixture
def store():
    """Fresh in-memory store for the agent/skill registry."""
    return InMemoryStore()


@pytest.fixture
def graph(store):
    """
    Compile graph with in-memory checkpointer and store for testing.

    This fixture provides a fresh graph instance for each test, ensuring test isolation.
    """
    return builder.compile(checkpointer=MemorySaver(), store=store)
