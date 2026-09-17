"""LangGraph single-node graph template.

Returns a predefined response. Replace logic and configuration as needed.
"""

from __future__ import annotations
from typing import Any, Dict
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.runtime import Runtime
from typing_extensions import TypedDict
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchRun
from deepagents import create_deep_agent
from src.agent.model import ModelAgent
import os


DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
search_tool = DuckDuckGoSearchRun()
model_agent = ModelAgent()
base_dir = os.path.dirname(os.path.abspath(__file__))


class Context(TypedDict, total=False):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """

    orchestrator_model: str  # e.g., "ollama:gemma4:31b-cloud"
    researcher_model: str
    coder_model: str


async def read_md_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def orchestrator_agent(state: MessagesState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "orchestrator", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("orchestrator_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_agent(
        model=model,
        tools=[],
        system_prompt=soul,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}


async def researcher_agent(state: MessagesState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "researcher", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("researcher_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        tools=[],
        system_prompt=soul,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}


async def coder_agent(state: MessagesState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "coder", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        tools=[],
        system_prompt=soul,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}


# Define the graph
builder = StateGraph(MessagesState, context_schema=Context)
builder.add_node(orchestrator_agent)
builder.add_node(researcher_agent)
builder.add_node(coder_agent)
builder.add_edge(START, "coder_agent")

# LangGraph API provides persistence automatically
# - langgraph dev: in-memory checkpointer
# - production deploy: PostgreSQL checkpointer (uses POSTGRES_URI from .env)
graph = builder.compile()
