"""Agent harness: one default-agent that creates agents and delegates to them.

The default-agent manages a registry of agents (system prompt, model, tools,
skills) stored in the LangGraph Store, and calls them as deepagents subagents
through the `task` tool. The deep agent is rebuilt every turn so agents created
in chat are picked up on the next message.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from deepagents import create_deep_agent
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.runtime import Runtime
from typing_extensions import TypedDict

from agent import registry
from agent.tools.manage import MANAGEMENT_TOOLS

base_dir = os.path.dirname(os.path.abspath(__file__))


class Context(TypedDict, total=False):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """

    default_model: str  # e.g., "ollama:gemma4:31b-cloud"


class HarnessState(MessagesState):
    """Conversation history."""


def read_soul(name: str) -> str:
    """Read souls/<name>/SOUL.md."""
    with open(os.path.join(base_dir, "souls", name, "SOUL.md"), encoding="utf-8") as f:
        return f.read()


async def default_agent(state: HarnessState, runtime: Runtime[Context]) -> Dict[str, Any]:
    """Build the default deep agent from the registry and run one turn."""
    store = runtime.store
    if store is None:
        raise RuntimeError("The agent harness needs a LangGraph store: compile with store=... or run via `langgraph dev`.")
    await registry.aseed(store)

    model_name = (runtime.context or {}).get("default_model", registry.DEFAULT_MODEL)
    agent = create_deep_agent(
        model=registry.load_model(model_name),
        tools=MANAGEMENT_TOOLS,
        system_prompt=read_soul("default"),
        subagents=registry.build_subagents(await registry.aget_agents(store)),
        backend=registry.make_backend(store),
        store=store,
    )
    # Pass full history so follow-ups can resolve earlier context
    history = state["messages"]
    result = await agent.ainvoke({"messages": history})
    seen_ids = {m.id for m in history}
    return {"messages": [m for m in result["messages"] if m.id not in seen_ids]}


builder = StateGraph(HarnessState, context_schema=Context)
builder.add_node("default_agent", default_agent)
builder.add_edge(START, "default_agent")
builder.add_edge("default_agent", END)

# LangGraph API provides persistence automatically
# - langgraph dev: in-memory checkpointer + store
# - production deploy: PostgreSQL checkpointer + store (uses POSTGRES_URI from .env)
graph = builder.compile()
