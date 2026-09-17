import asyncio, os
from tests.integration_tests.test_agent_flows import TestClearQueryFlows
from src.agent.graph import graph

os.environ["LANGSMITH_TRACING"] = 'true'
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_API_KEY"] = "api key"
os.environ["LANGSMITH_PROJECT"] = "test-dev"  # optional

flow_test = TestClearQueryFlows()
result = asyncio.run(flow_test.test_ambiguos_coder_flow(graph))