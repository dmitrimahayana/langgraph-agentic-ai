import asyncio, os

os.environ["LANGSMITH_TRACING"] = 'true'
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGSMITH_PROJECT"] = "test-dev"  # optional

os.environ["JIRA_API_TOKEN"] = ""
os.environ["JIRA_USERNAME"] = "email"
os.environ["JIRA_INSTANCE_URL"] = "https://company-name.atlassian.net"
os.environ["JIRA_CLOUD"] = "True"

os.environ["SLACK_BOT_TOKEN"] = ""
os.environ["SLACK_CHANNEL_ID"] = "id channel"

from tests.integration_tests.test_agent_flows import TestClearQueryFlows
from src.agent.graph import graph

flow_test = TestClearQueryFlows()
result = asyncio.run(flow_test.test_clear_slack_flow(graph))