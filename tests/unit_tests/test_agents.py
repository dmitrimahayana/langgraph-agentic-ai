"""Unit tests for researcher and coder agents."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from langchain_core.messages import HumanMessage, AIMessage

from agent.graph import researcher_agent, coder_agent

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_runtime():
    """Mock runtime with default context."""
    runtime = Mock()
    runtime.context = {
        "researcher_model": "ollama:gemma4:31b-cloud",
        "coder_model": "ollama:gemma4:31b-cloud"
    }
    return runtime


class TestResearcherAgent:
    """Test researcher agent behavior."""

    async def test_researcher_receives_messages(self, mock_runtime):
        """Researcher agent processes message history."""
        state = {
            "messages": [
                HumanMessage(content="Explain how bubble sort works")
            ]
        }

        mock_result = {
            "messages": state["messages"] + [
                AIMessage(
                    content="Bubble sort is a sorting algorithm that repeatedly "
                    "steps through the list..."
                )
            ]
        }

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = mock_result
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_llm = Mock()
                mock_instance = Mock()
                mock_instance.load_model.return_value = mock_llm
                mock_ma.return_value = mock_instance

                result = await researcher_agent(state, mock_runtime)

                # Verify messages returned
                assert "messages" in result
                assert len(result["messages"]) > len(state["messages"])

                # Verify results tracking
                assert "results" in result
                assert len(result["results"]) == 1
                assert result["results"][0]["source"] == "researcher"

    async def test_researcher_uses_search_tool(self, mock_runtime):
        """Researcher agent has access to search tool."""
        state = {"messages": [HumanMessage(content="Research AI trends")]}

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = {
                "messages": state["messages"] + [
                    AIMessage(content="Research results...")
                ]
            }
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                with patch("agent.graph.search_tool") as mock_search:
                    await researcher_agent(state, mock_runtime)

                    # Verify search tool was passed to agent
                    call_kwargs = mock_agent.call_args[1]
                    assert "tools" in call_kwargs
                    # Should have at least one tool (search_tool)
                    assert len(call_kwargs["tools"]) > 0

    async def test_researcher_maintains_conversation_context(self, mock_runtime):
        """Researcher maintains context across conversation."""
        state = {
            "messages": [
                HumanMessage(content="What is authentication?"),
                AIMessage(content="Authentication is..."),
                HumanMessage(content="What about JWT specifically?"),
            ]
        }

        mock_result = {
            "messages": state["messages"] + [
                AIMessage(content="JWT (JSON Web Token) is...")
            ]
        }

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = mock_result
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                result = await researcher_agent(state, mock_runtime)

                # Agent received full conversation history
                invoke_call = mock_agent_instance.ainvoke.call_args[0][0]
                assert "messages" in invoke_call
                assert len(invoke_call["messages"]) == len(state["messages"])


class TestCoderAgent:
    """Test coder agent behavior."""

    async def test_coder_receives_messages(self, mock_runtime):
        """Coder agent processes message history."""
        state = {
            "messages": [
                HumanMessage(content="Implement bubble sort in Python")
            ]
        }

        mock_result = {
            "messages": state["messages"] + [
                AIMessage(
                    content="Here's the bubble sort implementation:\n```python\n"
                    "def bubble_sort(arr):\n    ...\n```"
                )
            ]
        }

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = mock_result
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                result = await coder_agent(state, mock_runtime)

                # Verify messages returned
                assert "messages" in result
                assert len(result["messages"]) > len(state["messages"])

                # Verify results tracking
                assert "results" in result
                assert len(result["results"]) == 1
                assert result["results"][0]["source"] == "coder"

    async def test_coder_handles_debugging(self, mock_runtime):
        """Coder handles debugging tasks."""
        state = {
            "messages": [
                HumanMessage(content="Fix the 500 error in login endpoint")
            ]
        }

        mock_result = {
            "messages": state["messages"] + [
                AIMessage(content="Found the issue - missing error handling...")
            ]
        }

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = mock_result
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                result = await coder_agent(state, mock_runtime)

                assert "messages" in result
                assert result["results"][0]["source"] == "coder"

    async def test_coder_maintains_conversation_context(self, mock_runtime):
        """Coder maintains context from previous messages."""
        state = {
            "messages": [
                HumanMessage(content="What's wrong with the login?"),
                AIMessage(content="There's a 500 error..."),
                HumanMessage(content="Fix it"),
            ]
        }

        mock_result = {
            "messages": state["messages"] + [
                AIMessage(content="Fixed the login error by...")
            ]
        }

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = mock_result
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                result = await coder_agent(state, mock_runtime)

                # Agent received full conversation history
                invoke_call = mock_agent_instance.ainvoke.call_args[0][0]
                assert "messages" in invoke_call
                assert len(invoke_call["messages"]) == len(state["messages"])


class TestAgentConfiguration:
    """Test agent configuration and model handling."""

    async def test_researcher_uses_custom_model(self):
        """Researcher uses custom model from runtime context."""
        custom_runtime = Mock()
        custom_runtime.context = {"researcher_model": "ollama:custom-research"}

        state = {"messages": [HumanMessage(content="Test")]}

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = {
                "messages": state["messages"] + [AIMessage(content="Response")]
            }
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                await researcher_agent(state, custom_runtime)

                # Verify custom model used
                mock_ma.assert_called_once_with(model_name="ollama:custom-research")

    async def test_coder_uses_custom_model(self):
        """Coder uses custom model from runtime context."""
        custom_runtime = Mock()
        custom_runtime.context = {"coder_model": "ollama:custom-coder"}

        state = {"messages": [HumanMessage(content="Test")]}

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = {
                "messages": state["messages"] + [AIMessage(content="Response")]
            }
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                await coder_agent(state, custom_runtime)

                # Verify custom model used
                mock_ma.assert_called_once_with(model_name="ollama:custom-coder")

    async def test_agents_use_default_when_no_context(self):
        """Agents fall back to default model when context missing."""
        runtime_no_context = Mock()
        runtime_no_context.context = None

        state = {"messages": [HumanMessage(content="Test")]}

        with patch("agent.graph.create_deep_agent") as mock_agent:
            mock_agent_instance = AsyncMock()
            mock_agent_instance.ainvoke.return_value = {
                "messages": state["messages"] + [AIMessage(content="Response")]
            }
            mock_agent.return_value = mock_agent_instance

            with patch("agent.graph.ModelAgent") as mock_ma:
                mock_instance = Mock()
                mock_instance.load_model.return_value = Mock()
                mock_ma.return_value = mock_instance

                await researcher_agent(state, runtime_no_context)

                # Should use default
                mock_ma.assert_called_once_with(model_name="ollama:gemma4:31b-cloud")
