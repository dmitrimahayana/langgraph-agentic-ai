import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent.graph import builder


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def graph():
    """Compile graph with in-memory checkpointer for testing."""
    return builder.compile(checkpointer=MemorySaver())
