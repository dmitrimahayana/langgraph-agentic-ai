from agent.model import ModelAgent
from src.tools.jira.Jira import jira_tools
from deepagents import create_deep_agent

user_input=""
# Use context model or default (context can be None)
model = ModelAgent(model_name="ollama:gemma4:31b-cloud").load_model()
agent = create_deep_agent(
    model=model,
    tools=jira_tools,
)
# Invoke with conversation context - agent will see full message history
result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})