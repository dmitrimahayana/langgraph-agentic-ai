import asyncio
from dotenv import load_dotenv
load_dotenv()

from tests.integration_tests.test_agent_flows import TestClearQueryFlows
from src.agent.graph import graph

flow_test = TestClearQueryFlows()
result = asyncio.run(flow_test.test_clear_slack_flow(graph))