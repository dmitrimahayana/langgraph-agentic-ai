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


search = DuckDuckGoSearchRun()
tools = [search]


class Context(TypedDict):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """

    my_configurable_param: str

async def call_agent(state: MessagesState, runtime: Runtime[Context]) -> Dict[str, Any]:
    """Process input and returns output."""
    agent = create_agent(
        model="openrouter:minimax/minimax-m2.7:free",
        tools=[],
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}

async def call_agent_with_tools(state: MessagesState, runtime: Runtime[Context]) -> Dict[str, Any]:
    """Process input and returns output."""
    research_instructions = """You are an expert researcher. Your job is to conduct thorough research and then write a polished report.

    You have access to an internet search tool as your primary means of gathering information.

    ## `internet_search`

    Use this to run an internet search for a given query. You can specify the max number of results to return, the topic, and whether raw content should be included.
    """
    agent = create_agent(
        model="openrouter:minimax/minimax-m2.7:free",
        tools=tools,
        system_prompt=research_instructions,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}


# Define the graph
builder = StateGraph(MessagesState, context_schema=Context)
builder.add_node(call_agent_with_tools)
builder.add_edge(START, "call_agent_with_tools")

graph = builder.compile()
