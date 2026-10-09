"""Agent harness: one default agent that creates agents and delegates to them.

Every agent is a folder `src/agent/profile/<name>/` (see registry.py) with
souls/SOUL.md, tools/TOOLS.md and skills/. The `default` folder is the chat
entry point; all other folders become deepagents subagents reached through the
`task` tool. Folders are re-read every turn, so agents created in chat or
edited by hand are picked up on the next message.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from deepagents import create_deep_agent
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.runtime import Runtime
from typing_extensions import TypedDict

from agent import registry
from agent.core.catalog import resolve_tools
from agent.core.manage import MANAGEMENT_TOOLS


class Context(TypedDict, total=False):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """

    default_model: str  # overrides `model` in default/souls/SOUL.md, e.g. "ollama:gemma4:31b-cloud"


class HarnessState(MessagesState):
    """Conversation history."""


def build_default_agent(model_override: str | None = None):
    """Read all agent folders and build the default deep agent (blocking file I/O)."""
    specs = registry.list_agents()
    default = next((s for s in specs if s.name == registry.DEFAULT_AGENT), None)
    if default is None:
        raise RuntimeError(f"No '{registry.DEFAULT_AGENT}' agent folder in {registry.agents_dir()}.")
    others = [s for s in specs if s.name != registry.DEFAULT_AGENT]
    return create_deep_agent(
        model=registry.load_model(model_override or default.model),
        tools=MANAGEMENT_TOOLS + resolve_tools(default.tools),
        system_prompt=default.system_prompt,
        skills=[registry.skills_source(default.name)],
        subagents=registry.build_subagents(others),
        backend=registry.make_backend(specs),
        permissions=registry.permissions_for(default),
        middleware=registry.model_middleware(),
    )


async def default_agent(state: HarnessState, runtime: Runtime[Context]) -> Dict[str, Any]:
    """Build the default deep agent from the agent folders and run one turn."""
    model_override = (runtime.context or {}).get("default_model")
    agent = await asyncio.to_thread(build_default_agent, model_override)
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
# - langgraph dev: in-memory checkpointer
# - production deploy: PostgreSQL checkpointer (uses POSTGRES_URI from .env)
# Agent folders live in src/agent/profile/: mount it as a persistent volume in prod.
graph = builder.compile()
