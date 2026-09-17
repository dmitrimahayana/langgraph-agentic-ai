"""Integration tests for full agent workflows."""

import pytest

pytestmark = pytest.mark.anyio


class TestClearQueryFlows:
    """Test complete flows for clear, unambiguous queries."""

    async def test_clear_coder_flow(self, graph):
        """
        Clear research query: orchestrator → classifier → researcher.

        Query: "Explain how bubble sort works"
        Expected: Routes to researcher for explanation
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "create implementation of binary search in python"}
                ]
            },
            config={"configurable": {"thread_id": "test-clear-coder-task"}},
        )

        # Verify response
        assert result["messages"]
        assert len(result["messages"]) >= 2  # At least user + assistant
    
    async def test_ambiguos_coder_flow(self, graph):
        """
        Clear research query: orchestrator → classifier → researcher.

        Query: "Explain how bubble sort works"
        Expected: Routes to researcher for explanation
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Improve the authentication system"}
                ]
            },
            config={"configurable": {"thread_id": "test-ambiguos-coder-task"}},
        )

        # Verify response
        assert result["messages"]
        assert len(result["messages"]) >= 2  # At least user + assistant

    async def test_clear_research_internet_flow(self, graph):
        """
        Clear research query: orchestrator → classifier → researcher.

        Query: "Explain how bubble sort works"
        Expected: Routes to researcher for explanation
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "what bitcoin price today"}
                ]
            },
            config={"configurable": {"thread_id": "test-clear-research"}},
        )

        # Verify response
        assert result["messages"]
        assert len(result["messages"]) >= 2  # At least user + assistant

    async def test_clear_research_query_flow(self, graph):
        """
        Clear research query: orchestrator → classifier → researcher.

        Query: "Explain how bubble sort works"
        Expected: Routes to researcher for explanation
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Explain how bubble sort algorithm works"}
                ]
            },
            config={"configurable": {"thread_id": "test-clear-research"}},
        )

        # Verify response
        assert result["messages"]
        assert len(result["messages"]) >= 2  # At least user + assistant

        # Verify classifications happened
        assert "classifications" in result
        assert len(result["classifications"]) > 0

        # Verify routed to researcher
        classifications = result["classifications"]
        assert any(c["source"] == "researcher" for c in classifications)

        # Verify results from researcher
        if "results" in result and result["results"]:
            assert any(r["source"] == "researcher" for r in result["results"])

    async def test_clear_coding_query_flow(self, graph):
        """
        Clear coding query: orchestrator → classifier → coder.

        Query: "Implement bubble sort in Python"
        Expected: Routes to coder for implementation
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Implement bubble sort in Python"}
                ]
            },
            config={"configurable": {"thread_id": "test-clear-coding"}},
        )

        assert result["messages"]
        assert "classifications" in result

        # Verify routed to coder
        classifications = result["classifications"]
        assert any(c["source"] == "coder" for c in classifications)

        # Verify results from coder
        if "results" in result and result["results"]:
            assert any(r["source"] == "coder" for r in result["results"])

    async def test_bug_fix_query_flow(self, graph):
        """
        Bug fix query: orchestrator → classifier → coder.

        Query: "Fix the authentication error"
        Expected: Routes to coder for debugging
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Fix the 500 error in the login endpoint"}
                ]
            },
            config={"configurable": {"thread_id": "test-bug-fix"}},
        )

        assert result["messages"]
        assert "classifications" in result

        # Bug fixes go to coder
        classifications = result["classifications"]
        assert any(c["source"] == "coder" for c in classifications)


class TestAmbiguousQueryFlows:
    """Test flows for ambiguous queries requiring clarification."""

    async def test_ambiguous_improvement_query(self, graph):
        """
        Ambiguous query: "Improve authentication"
        Expected: Orchestrator may ask for clarification OR classifier routes based on context
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Improve the authentication system"}
                ]
            },
            config={"configurable": {"thread_id": "test-ambiguous-improve"}},
        )

        assert result["messages"]

        # Response should either:
        # 1. Ask for clarification (orchestrator)
        # 2. Make a routing decision (classifier)
        last_message = result["messages"][-1].content.lower()

        # Check if asking for clarification
        asking_clarification = any(
            phrase in last_message
            for phrase in ["clarify", "can you", "do you want", "are you looking"]
        )

        # Or made a routing decision
        has_classification = "classifications" in result and len(result["classifications"]) > 0

        # One of these should be true
        assert asking_clarification or has_classification

    async def test_vague_query_handling(self, graph):
        """
        Vague query: "Fix the app"
        Expected: Request for more details
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Fix the app"}
                ]
            },
            config={"configurable": {"thread_id": "test-vague"}},
        )

        assert result["messages"]

        # Should handle vague request - either ask for details or route based on context
        last_message = result["messages"][-1].content.lower()
        has_response = len(last_message) > 0

        assert has_response


class TestFollowUpQueryFlows:
    """Test flows for follow-up queries with conversation context."""

    async def test_research_then_implement_flow(self, graph):
        """
        Follow-up flow: Research → then implement based on research.

        1. User: "Explain authentication"  → researcher
        2. User: "Now implement it"        → coder
        """
        config = {"configurable": {"thread_id": "test-research-then-code"}}

        # First: research query
        result1 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Explain how JWT authentication works"}
                ]
            },
            config=config,
        )

        assert result1["messages"]
        # Should route to researcher initially
        if "classifications" in result1 and result1["classifications"]:
            assert any(c["source"] == "researcher" for c in result1["classifications"])

        # Second: follow-up to implement
        result2 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Now implement JWT authentication in our API"}
                ]
            },
            config=config,
        )

        assert result2["messages"]
        # Follow-up should route to coder
        if "classifications" in result2 and result2["classifications"]:
            # Get the most recent classification
            last_classification = result2["classifications"][-1]
            assert last_classification["source"] == "coder"

    async def test_debugging_follow_up_flow(self, graph):
        """
        Debugging follow-up: Report issue → explain error → fix it.

        1. User: "Login returns 500"      → coder (diagnose)
        2. User: "What caused it?"        → researcher (explain)
        3. User: "Fix it now"             → coder (implement fix)
        """
        config = {"configurable": {"thread_id": "test-debug-followup"}}

        # First: report issue
        result1 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "The login endpoint returns 500 error"}
                ]
            },
            config=config,
        )

        assert result1["messages"]

        # Second: ask for explanation
        result2 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "What's causing that error?"}
                ]
            },
            config=config,
        )

        assert result2["messages"]
        # Explanation might go to researcher or coder depending on context

        # Third: request fix
        result3 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Fix it"}
                ]
            },
            config=config,
        )

        assert result3["messages"]
        # Fix should go to coder
        if "classifications" in result3 and result3["classifications"]:
            last_classification = result3["classifications"][-1]
            # Should route to coder for implementation
            assert last_classification["source"] in ["coder", "researcher"]

    async def test_conversation_context_maintained(self, graph):
        """
        Verify conversation context flows through all agents.

        Multi-turn conversation should maintain context throughout.
        """
        config = {"configurable": {"thread_id": "test-context-flow"}}

        # Turn 1
        result1 = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "What is bubble sort?"}]},
            config=config,
        )

        assert result1["messages"]
        initial_msg_count = len(result1["messages"])

        # Turn 2 - context should include previous messages
        result2 = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "How is it different from quick sort?"}]},
            config=config,
        )

        assert result2["messages"]
        # Message count should include history
        assert len(result2["messages"]) >= initial_msg_count

        # Turn 3 - more context
        result3 = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "Implement bubble sort"}]},
            config=config,
        )

        assert result3["messages"]
        # Should maintain full conversation history
        assert len(result3["messages"]) >= len(result2["messages"])


class TestExplainVsImplementDistinction:
    """Test classifier correctly distinguishing 'explain how' vs 'implement'."""

    async def test_explain_how_to_create_routes_to_researcher(self, graph):
        """
        'Can you tell me how to create X' = explanation = researcher.

        User wants to learn, not have code written.
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Can you tell me how to create logic bubble sort in C++?"
                    }
                ]
            },
            config={"configurable": {"thread_id": "test-explain-how-to"}},
        )

        assert result["messages"]
        assert "classifications" in result

        # "tell me how to create" = wants explanation
        classifications = result["classifications"]
        assert any(c["source"] == "researcher" for c in classifications)

    async def test_create_or_implement_routes_to_coder(self, graph):
        """
        'Create X' or 'Implement X' = action = coder.

        User wants code written.
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Create a bubble sort function in C++"}
                ]
            },
            config={"configurable": {"thread_id": "test-create-implement"}},
        )

        assert result["messages"]
        assert "classifications" in result

        # Direct "create" = wants code
        classifications = result["classifications"]
        assert any(c["source"] == "coder" for c in classifications)

    async def test_how_does_x_work_routes_to_researcher(self, graph):
        """
        'How does X work' = conceptual = researcher.
        """
        result = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "How does binary search work?"}
                ]
            },
            config={"configurable": {"thread_id": "test-how-does-work"}},
        )

        assert result["messages"]
        assert "classifications" in result

        classifications = result["classifications"]
        assert any(c["source"] == "researcher" for c in classifications)


class TestMultiThreadIsolation:
    """Test that different conversation threads remain isolated."""

    async def test_threads_dont_share_context(self, graph):
        """Different thread IDs should have isolated conversations."""
        # Thread A: discuss authentication
        result_a1 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Explain JWT authentication"}
                ]
            },
            config={"configurable": {"thread_id": "thread-a"}},
        )

        assert result_a1["messages"]

        # Thread B: discuss sorting - should NOT have JWT context
        result_b1 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "Implement bubble sort"}
                ]
            },
            config={"configurable": {"thread_id": "thread-b"}},
        )

        assert result_b1["messages"]

        # Thread B follow-up should not reference JWT from Thread A
        result_b2 = await graph.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": "What were we discussing?"}
                ]
            },
            config={"configurable": {"thread_id": "thread-b"}},
        )

        last_msg = result_b2["messages"][-1].content.lower()
        # Should reference sorting, not JWT
        assert "sort" in last_msg or "bubble" in last_msg
        assert "jwt" not in last_msg and "authentication" not in last_msg
