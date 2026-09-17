"""Unit tests for orchestrator agent."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from langchain_core.messages import HumanMessage, AIMessage

from agent.graph import orchestrator_agent, RouterState

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_runtime():
    """Mock runtime with default context."""
    runtime = Mock()
    runtime.context = {"orchestrator_model": "ollama:gemma4:31b-cloud"}
    return runtime


@pytest.fixture
def mock_model_agent():
    """Mock ModelAgent that returns a mock LLM."""
    with patch("agent.graph.ModelAgent") as mock:
        mock_llm = AsyncMock()
        mock_instance = Mock()
        mock_instance.load_model.return_value = mock_llm
        mock.return_value = mock_instance
        yield mock_llm


@pytest.fixture
def mock_create_agent():
    """Mock create_agent function."""
    with patch("agent.graph.create_agent") as mock:
        mock_agent = AsyncMock()
        mock.return_value = mock_agent
        yield mock_agent


class TestOrchestratorClearQuery:
    """Test orchestrator handling clear, unambiguous queries."""

    async def test_clear_research_query(
        self, mock_runtime, mock_model_agent, mock_create_agent
    ):
        """Orchestrator processes clear research query."""
        # Setup
        state = {
            "messages": [
                HumanMessage(content="Explain how bubble sort works")
            ]
        }

        # Mock agent response
        mock_create_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="Explain how bubble sort works"),
                AIMessage(
                    content="Understood - routing to researcher to explain bubble sort algorithm."
                ),
            ]
        }

        # Execute
        result = await orchestrator_agent(state, mock_runtime)

        # Verify
        assert "messages" in result
        assert len(result["messages"]) >= 1
        mock_create_agent.ainvoke.assert_called_once()

    async def test_clear_coding_query(
        self, mock_runtime, mock_model_agent, mock_create_agent
    ):
        """Orchestrator processes clear coding query."""
        state = {
            "messages": [
                HumanMessage(content="Implement bubble sort in Python")
            ]
        }

        mock_create_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="Implement bubble sort in Python"),
                AIMessage(
                    content="Understood - routing to coder to implement bubble sort."
                ),
            ]
        }

        result = await orchestrator_agent(state, mock_runtime)

        assert "messages" in result
        assert len(result["messages"]) >= 1


class TestOrchestratorAmbiguousQuery:
    """Test orchestrator handling ambiguous queries that need clarification."""

    async def test_ambiguous_improvement_query(
        self, mock_runtime, mock_model_agent, mock_create_agent
    ):
        """Orchestrator asks for clarification on vague 'improve' request."""
        state = {
            "messages": [
                HumanMessage(content="Improve the authentication system")
            ]
        }

        mock_create_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="Improve the authentication system"),
                AIMessage(
                    content="To route this correctly, can you clarify: are you looking "
                    "for an explanation of current auth (research) or implementing "
                    "improvements (coding)?"
                ),
            ]
        }

        result = await orchestrator_agent(state, mock_runtime)

        assert "messages" in result
        response_content = result["messages"][-1].content
        # Should ask for clarification
        assert "clarify" in response_content.lower() or "research" in response_content.lower()

    async def test_ambiguous_vague_query(
        self, mock_runtime, mock_model_agent, mock_create_agent
    ):
        """Orchestrator handles vague request without enough context."""
        state = {
            "messages": [
                HumanMessage(content="Fix the app")
            ]
        }

        mock_create_agent.ainvoke.return_value = {
            "messages": [
                HumanMessage(content="Fix the app"),
                AIMessage(
                    content="Can you provide more details? What specifically needs to be fixed?"
                ),
            ]
        }

        result = await orchestrator_agent(state, mock_runtime)

        assert "messages" in result


class TestOrchestratorFollowUpQuery:
    """Test orchestrator handling follow-up queries with conversation context."""

    async def test_follow_up_with_context(
        self, mock_runtime, mock_model_agent, mock_create_agent
    ):
        """Orchestrator maintains context in follow-up query."""
        state = {
            "messages": [
                HumanMessage(content="Explain how authentication works"),
                AIMessage(content="Routing to researcher..."),
                AIMessage(content="Authentication uses JWT tokens..."),
                HumanMessage(content="Now implement it in our API"),
            ]
        }

        mock_create_agent.ainvoke.return_value = {
            "messages": state["messages"] + [
                AIMessage(
                    content="Continuing from our authentication discussion - "
                    "routing to coder to implement JWT in the API."
                )
            ]
        }

        result = await orchestrator_agent(state, mock_runtime)

        assert "messages" in result
        response = result["messages"][-1].content
        # Should reference previous context
        assert "authentication" in response.lower() or "jwt" in response.lower()

    async def test_follow_up_debugging(
        self, mock_runtime, mock_model_agent, mock_create_agent
    ):
        """Orchestrator handles debugging follow-up."""
        state = {
            "messages": [
                HumanMessage(content="The login endpoint returns 500"),
                AIMessage(content="Routing to coder..."),
                AIMessage(content="Found the issue in auth middleware..."),
                HumanMessage(content="What caused that error?"),
            ]
        }

        mock_create_agent.ainvoke.return_value = {
            "messages": state["messages"] + [
                AIMessage(
                    content="Following up on the login 500 error - "
                    "routing to researcher to explain the root cause."
                )
            ]
        }

        result = await orchestrator_agent(state, mock_runtime)

        assert "messages" in result


class TestOrchestratorContextHandling:
    """Test orchestrator's context and configuration handling."""

    async def test_uses_custom_model_from_context(
        self, mock_model_agent, mock_create_agent
    ):
        """Orchestrator uses custom model when specified in context."""
        custom_runtime = Mock()
        custom_runtime.context = {"orchestrator_model": "ollama:custom-model"}

        state = {"messages": [HumanMessage(content="Test query")]}

        mock_create_agent.ainvoke.return_value = {
            "messages": state["messages"] + [AIMessage(content="Response")]
        }

        with patch("agent.graph.ModelAgent") as mock_ma:
            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_model_agent
            mock_ma.return_value = mock_instance

            await orchestrator_agent(state, custom_runtime)

            # Verify ModelAgent was initialized with custom model
            mock_ma.assert_called_once_with(model_name="ollama:custom-model")

    async def test_uses_default_model_when_no_context(
        self, mock_model_agent, mock_create_agent
    ):
        """Orchestrator falls back to default model when no context."""
        runtime_no_context = Mock()
        runtime_no_context.context = None

        state = {"messages": [HumanMessage(content="Test query")]}

        mock_create_agent.ainvoke.return_value = {
            "messages": state["messages"] + [AIMessage(content="Response")]
        }

        with patch("agent.graph.ModelAgent") as mock_ma:
            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_model_agent
            mock_ma.return_value = mock_instance

            await orchestrator_agent(state, runtime_no_context)

            # Should use default model
            mock_ma.assert_called_once_with(model_name="ollama:gemma4:31b-cloud")
