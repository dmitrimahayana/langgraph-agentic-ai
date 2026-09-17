"""LangGraph single-node graph template.

Returns a predefined response. Replace logic and configuration as needed.
"""

from __future__ import annotations
from typing import Any, Dict, Literal, Annotated
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.runtime import Runtime
from typing_extensions import TypedDict
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchRun
from deepagents import create_deep_agent
from agent.model import ModelAgent
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field
from langgraph.types import Send
import operator
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


class Classification(TypedDict):
    """A single routing decision: which agent to call with what query."""
    source: Literal["researcher", "coder"]
    query: str


class AgentOutput(TypedDict):
    """Output from each subagent."""
    source: str
    result: str


class RouterState(MessagesState):
    """State that maintains conversation history via messages."""
    classifications: list[Classification]
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results


# Define structured output schema for the classifier
class ClassificationResult(BaseModel):
    """Result of classifying a user query into agent-specific sub-questions."""
    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )


async def read_md_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def orchestrator_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
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


async def classify_query(state: RouterState, runtime: Runtime[Context]) -> dict:
    """Classify query and determine which agents to invoke."""
    from langchain_core.messages import SystemMessage

    file_path = os.path.join(base_dir, "souls", "router", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("orchestrator_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    structured_llm = model.with_structured_output(ClassificationResult)

    # Build messages with system prompt + conversation history
    messages = [SystemMessage(content=soul)] + state["messages"]

    # Call structured LLM directly (not via create_agent)
    result = await structured_llm.ainvoke(messages)

    return {"classifications": result.classifications}


async def route_to_agents(state: RouterState) -> list[Send]:
    """Fan out to agents based on classifications."""
    return [
        Send(c["source"], {"messages": state["messages"], "query": c["query"]})
        for c in state["classifications"]
    ]


async def researcher_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "researcher", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("researcher_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        tools=[search_tool],
        system_prompt=soul,
    )

    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state["messages"]})

    # Return results with source tracking
    return {
        "messages": result["messages"],
        "results": [{"source": "researcher", "result": str(result["messages"][-1].content)}]
    }


async def coder_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
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

    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state["messages"]})

    # Return results with source tracking
    return {
        "messages": result["messages"],
        "results": [{"source": "coder", "result": str(result["messages"][-1].content)}]
    }


# Define the graph
builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("orchestrator", orchestrator_agent)
builder.add_node("researcher", researcher_agent)
builder.add_node("coder", coder_agent)
builder.add_node("classifier", classify_query)
builder.add_conditional_edges("classifier", route_to_agents, ["researcher", "coder"])


# Start with orchestrator
builder.add_edge(START, "orchestrator")
builder.add_edge("orchestrator", "classifier")

# After specialist agents complete, go to END
builder.add_edge("researcher", END)
builder.add_edge("coder", END)

# LangGraph API provides persistence automatically
# - langgraph dev: in-memory checkpointer
# - production deploy: PostgreSQL checkpointer (uses POSTGRES_URI from .env)
graph = builder.compile()
