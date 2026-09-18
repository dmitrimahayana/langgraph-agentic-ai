"""LangGraph single-node graph template.

Returns a predefined response. Replace logic and configuration as needed.
"""

from __future__ import annotations
from typing import Any, Dict, Literal, Annotated
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain.tools import tool, ToolRuntime
from langgraph.runtime import Runtime
from typing_extensions import TypedDict
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.agent_toolkits.jira.toolkit import JiraToolkit
from langchain_community.utilities.jira import JiraAPIWrapper
from deepagents.backends import StateBackend
from deepagents import create_deep_agent
from agent.model import ModelAgent
from langchain.messages import ToolMessage, HumanMessage
from pydantic import BaseModel, Field
from langgraph.types import Send, Command
import operator
import os

# Send(): Jump/Delegate
# Directly transitions execution to the target node and continues along 
# the new graph path. Does not return to the caller node.

# Command(): Invoke & Return
# Calls a specific node like a subroutine and returns back to the caller 
# once finished. The invoked node can directly alter/update the State. the caller then read the altered State

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
search_tool = DuckDuckGoSearchRun()
jira_api = JiraAPIWrapper()
jira_toolkit = JiraToolkit.from_jira_api_wrapper(jira_api)
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

class Progress(BaseModel):
    progress: Literal["NEXT_STEP", "END"] = Field()

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
    check_progress: str
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results


# Define structured output schema for the classifier
class ClassificationResult(BaseModel):
    """Result of classifying a user query into agent-specific sub-questions."""
    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )

# Agent wrap tool
@tool
def handoff_to_researcher_agent(task: str, runtime: ToolRuntime) -> Command:
    """Delegate internet research and reference tasks to the researcher agent.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="researcher",
        update={"messages": [ToolMessage(
            content=f"Handed off to researcher with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )

@tool
def handoff_to_coder_agent(task: str, runtime: ToolRuntime) -> Command:
    """Delegate coding and filesystem tasks to the coder agent.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="coder",
        update={"messages": [ToolMessage(
            content=f"Handed off to coder with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )

@tool
def handoff_to_jira_agent(task: str, runtime: ToolRuntime) -> Command:
    """Delegate jira management tasks to the jira agent.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="jira",
        update={"messages": [ToolMessage(
            content=f"Handed off to jira with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
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
        tools=[
            handoff_to_researcher_agent,
            handoff_to_coder_agent,
            handoff_to_jira_agent
            ],
        system_prompt=soul,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}


async def researcher_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "researcher", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("researcher_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_agent(
        model=model,
        tools=[search_tool],
        system_prompt=soul,
    )
    last_msg = state["messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [human_msg]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
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
        backend=StateBackend()
    )
    last_msg = state["messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [human_msg]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
    # Return results with source tracking
    return {
        "messages": result["messages"],
        "results": [{"source": "coder", "result": str(result["messages"][-1].content)}]
    }

async def jira_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "jira", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("jira_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    tools = jira_toolkit.get_tools()

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=soul,
    )
    last_msg = state["messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [human_msg]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
    # Return results with source tracking
    return {
        "messages": result["messages"],
        "results": [{"source": "jira", "result": str(result["messages"][-1].content)}]
    }

async def evaluator(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "evaluator", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("evaluator", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_agent(
        model=model,
        system_prompt=soul
    )
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state["messages"]})

    # Return results with source tracking
    return {"check_progress": result["messages"][-1].content}

def progress_router(state: RouterState):
    if state["check_progress"] == "NEXT_STEP":
        return "NEXT"
    elif state["check_progress"] == "END":
        return "END"

# Define the graph
builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("orchestrator", orchestrator_agent)
builder.add_node("researcher", researcher_agent)
builder.add_node("coder", coder_agent)
builder.add_node("jira", jira_agent)
builder.add_node("evaluator", evaluator)
# builder.add_node("classifier", classify_query)
# builder.add_conditional_edges("classifier", route_to_agents, ["researcher", "coder"])


# Start with orchestrator
builder.add_edge(START, "orchestrator")
builder.add_edge("orchestrator", "evaluator")
builder.add_conditional_edges(
    "evaluator",
    progress_router,
    {
        "NEXT": "orchestrator",
        "END": END
    },
)

# After specialist agents complete, go to END
# builder.add_edge("researcher", END)
# builder.add_edge("coder", END)

# LangGraph API provides persistence automatically
# - langgraph dev: in-memory checkpointer
# - production deploy: PostgreSQL checkpointer (uses POSTGRES_URI from .env)
graph = builder.compile()
