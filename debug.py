import asyncio, os

os.environ["LANGSMITH_TRACING"] = 'true'
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_API_KEY"] = "api key"
os.environ["LANGSMITH_PROJECT"] = "test-dev"  # optional

os.environ["JIRA_API_TOKEN"] = "api token"
os.environ["JIRA_USERNAME"] = "email"
os.environ["JIRA_INSTANCE_URL"] = "instance url"
os.environ["JIRA_CLOUD"] = "True"

from tests.integration_tests.test_agent_flows import TestClearQueryFlows
from src.agent.graph import graph

flow_test = TestClearQueryFlows()
result = asyncio.run(flow_test.test_clear_jira_flow(graph))