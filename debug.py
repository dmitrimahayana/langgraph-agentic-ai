import asyncio
from tests.integration_tests.test_agent_flows import TestClearQueryFlows
from src.agent.graph import graph
flow_test = TestClearQueryFlows()
result = asyncio.run(flow_test.test_clear_research_query_flow(graph))