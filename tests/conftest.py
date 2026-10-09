import shutil

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agent import registry
from agent.graph import builder


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio to use asyncio backend for async tests."""
    return "asyncio"


@pytest.fixture(autouse=True)
def agents_dir(tmp_path, monkeypatch):
    """Copy of src/agent/profile in a temp dir, so tests never write into src/."""
    path = tmp_path / "profile"
    shutil.copytree(registry.PROFILE_DIR, path, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(registry, "PROFILE_DIR", path)
    monkeypatch.setattr(registry, "WORKSPACE_DIR", tmp_path / "workspace")
    return path


@pytest.fixture
def graph():
    """
    Compile graph with in-memory checkpointer for testing.

    This fixture provides a fresh graph instance for each test, ensuring test isolation.
    """
    return builder.compile(checkpointer=MemorySaver())
