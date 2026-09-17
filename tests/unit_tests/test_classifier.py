"""Unit tests for classifier/router agent."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from agent.graph import classify_query, ClassificationResult, Classification

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_runtime():
    """Mock runtime with default context."""
    runtime = Mock()
    runtime.context = {"orchestrator_model": "ollama:gemma4:31b-cloud"}
    return runtime


class TestClassifierClearQueries:
    """Test classifier routing clear, unambiguous queries."""

    async def test_classify_clear_research_query(self, mock_runtime):
        """Classifier routes clear research query to researcher."""
        state = {
            "messages": [
                HumanMessage(content="Explain how bubble sort algorithm works")
            ]
        }

        # Mock the structured LLM output
        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="researcher",
                    query="Explain bubble sort algorithm logic and implementation"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            # Verify classification
            assert "classifications" in result
            assert len(result["classifications"]) == 1
            assert result["classifications"][0]["source"] == "researcher"
            assert "bubble sort" in result["classifications"][0]["query"].lower()

    async def test_classify_clear_coding_query(self, mock_runtime):
        """Classifier routes clear coding query to coder."""
        state = {
            "messages": [
                HumanMessage(content="Implement JWT authentication in the API")
            ]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="coder",
                    query="Implement JWT authentication middleware for API endpoints"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            assert result["classifications"][0]["source"] == "coder"
            assert "jwt" in result["classifications"][0]["query"].lower()

    async def test_classify_bug_fix_to_coder(self, mock_runtime):
        """Classifier routes bug fix to coder."""
        state = {
            "messages": [
                HumanMessage(content="Fix the 500 error in login endpoint")
            ]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="coder",
                    query="Debug and fix 500 error in login endpoint"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            assert result["classifications"][0]["source"] == "coder"


class TestClassifierExplainVsImplement:
    """Test classifier distinguishing between 'explain how' vs 'implement'."""

    async def test_explain_how_to_implement_routes_to_researcher(self, mock_runtime):
        """'Explain how to implement X' should go to researcher."""
        state = {
            "messages": [
                HumanMessage(content="Can you tell me how to create logic bubble sort in C++?")
            ]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="researcher",
                    query="Explain bubble sort algorithm logic and how to implement it in C++"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            # "tell me how to" = explanation = researcher
            assert result["classifications"][0]["source"] == "researcher"

    async def test_implement_routes_to_coder(self, mock_runtime):
        """'Implement X' should go to coder."""
        state = {
            "messages": [
                HumanMessage(content="Implement bubble sort in C++")
            ]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="coder",
                    query="Write bubble sort implementation in C++"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            # Direct "implement" = coder
            assert result["classifications"][0]["source"] == "coder"

    async def test_how_does_x_work_routes_to_researcher(self, mock_runtime):
        """'How does X work' should go to researcher."""
        state = {
            "messages": [
                HumanMessage(content="How does our authentication system work?")
            ]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="researcher",
                    query="Explain how the authentication system works"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            assert result["classifications"][0]["source"] == "researcher"


class TestClassifierFollowUpQueries:
    """Test classifier handling follow-up queries with context."""

    async def test_follow_up_maintains_context(self, mock_runtime):
        """Classifier considers conversation history for follow-ups."""
        state = {
            "messages": [
                HumanMessage(content="Explain authentication"),
                AIMessage(content="Auth uses JWT tokens..."),
                HumanMessage(content="Now implement it"),
            ]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(
                    source="coder",
                    query="Implement JWT authentication based on previous explanation"
                )
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            # "Now implement it" after explanation = coder
            assert result["classifications"][0]["source"] == "coder"

            # Verify messages passed to structured LLM include history
            call_args = mock_structured_llm.ainvoke.call_args[0][0]
            # Should have system message + conversation messages
            assert any(isinstance(msg, SystemMessage) for msg in call_args)
            assert len([m for m in call_args if isinstance(m, HumanMessage)]) >= 2


class TestClassifierStructuredOutput:
    """Test classifier returns proper structured output format."""

    async def test_returns_valid_classification_structure(self, mock_runtime):
        """Classifier returns dict with 'classifications' key."""
        state = {
            "messages": [HumanMessage(content="Test query")]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(source="researcher", query="Test")
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            # Verify structure
            assert isinstance(result, dict)
            assert "classifications" in result
            assert isinstance(result["classifications"], list)
            assert len(result["classifications"]) > 0
            assert "source" in result["classifications"][0]
            assert "query" in result["classifications"][0]

    async def test_classification_source_is_valid(self, mock_runtime):
        """Classification source must be 'researcher' or 'coder'."""
        state = {
            "messages": [HumanMessage(content="Test")]
        }

        mock_result = ClassificationResult(
            classifications=[
                Classification(source="researcher", query="Test")
            ]
        )

        with patch("agent.graph.ModelAgent") as mock_ma:
            # Mock the structured LLM
            mock_structured_llm = AsyncMock()
            mock_structured_llm.ainvoke.return_value = mock_result

            # Mock the base LLM with sync with_structured_output method
            mock_llm = Mock()
            mock_llm.with_structured_output = Mock(return_value=mock_structured_llm)

            mock_instance = Mock()
            mock_instance.load_model.return_value = mock_llm
            mock_ma.return_value = mock_instance

            result = await classify_query(state, mock_runtime)

            source = result["classifications"][0]["source"]
            assert source in ["researcher", "coder"]
