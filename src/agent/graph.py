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
from langchain_community.tools.tavily_search import TavilySearchResults
from deepagents.backends import StateBackend, FilesystemBackend
from langchain.agents.middleware import HumanInTheLoopMiddleware 
from deepagents import create_deep_agent
from agent.model import ModelAgent
from langchain.messages import ToolMessage, HumanMessage
from pydantic import BaseModel, Field
from langgraph.types import Command, Send
from src.tools.jira.Jira import jira_tools
from langsmith.sandbox import SandboxClient
from deepagents.backends import LangSmithSandbox
import operator
import os

# Send(): Jump/Delegate
# Directly transitions execution to the target node and continues along 
# the new graph path. Does not return to the caller node.

# Command(): Invoke & Return
# Calls a specific node like a subroutine and returns back to the caller 
# once finished. The invoked node can directly alter/update the State. the caller then read the altered State

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
base_dir = os.path.dirname(os.path.abspath(__file__))
# client = SandboxClient()  # DEV: disabled to avoid quota
# ls_sandbox = client.create_sandbox()  # DEV: disabled to avoid quota
# backend = LangSmithSandbox(sandbox=ls_sandbox) # PROD
backend = StateBackend() # DEV

# Lazy initialization for search tool - requires TAVILY_API_KEY env var
_search_tool = None
def get_search_tool():
    global _search_tool
    if _search_tool is None:
        _search_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
        )
    return _search_tool

# Lazy initialization for Jira - only create when needed
# _jira_toolkit = None
# def get_jira_toolkit():
#     global _jira_toolkit
#     if _jira_toolkit is None:
#         jira_api = JiraAPIWrapper()
#         _jira_toolkit = JiraToolkit.from_jira_api_wrapper(jira_api)
#     return _jira_toolkit


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
    ticket_key: str = ''
    project_key: str = ''
    ticket_url: str = ''
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results


# Define structured output schema for the classifier
class ClassificationResult(BaseModel):
    """Result of classifying a user query into agent-specific sub-questions."""
    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )

# File system tools
@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file at the specified path.

    Args:
        file_path: The path where the file should be written
        content: The content to write to the file

    Returns:
        Success message with file path
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing to {file_path}: {str(e)}"

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
        goto="coding_planner",
        update={"messages": [ToolMessage(
            content=f"Handed off to coding planner with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )

@tool
def handoff_from_planner_to_coder(task: str, runtime: ToolRuntime) -> Command:
    """Hand off from coding planner to coder agent with implementation plan.
    Provide the detailed plan and task description.
    """
    return Command(
        goto="coder",
        update={"messages": [ToolMessage(
            content=f"Handed off to coder from planner: {task}",
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

@tool
def activate_jira_mode(
    ticket_key: str,
    project_key: str,
    ticket_url: str,
    runtime: ToolRuntime
) -> Command:
    """Activate this tool when the user assigns you to a Jira task.

    Args:
        ticket_key: The Jira issue key this task relates to (e.g. "ABC-123").
            Required so the downstream agent knows exactly which ticket to
            work on, since it has no access to prior conversation history.
        project_key: Optional. The Jira project key (e.g. "ABC"), useful if
            it isn't already implied by ticket_key or needs to be
            disambiguated.
        ticket_url: Optional. Direct URL to the Jira ticket, if available,
            so the agent can open it directly instead of searching for it.
    """
    return Command(
        update={
            "messages": [ToolMessage(content=f"activating jira mode",tool_call_id=runtime.tool_call_id)],
            "ticket_key": ticket_key,
            "project_key": project_key,
            "ticket_url": ticket_url,
        },
        graph=Command.PARENT
    )

@tool
def deactivate_jira_mode(
    runtime: ToolRuntime
) -> Command:
    """Activate this tool when the assigned jira task is finished."""
    return Command(
        update={
            "messages": [ToolMessage(content=f"deactivating jira mode",tool_call_id=runtime.tool_call_id)],
            "ticket_key": "",
            "project_key": "",
            "ticket_url": "",
        },
        graph=Command.PARENT
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
            activate_jira_mode,
            handoff_to_researcher_agent,
            handoff_to_coder_agent,
            handoff_to_jira_agent
            ],
        system_prompt=soul,
    )
    result = await agent.ainvoke({"messages": state["messages"]})

    return {"messages": result["messages"]}

async def jira_mode_orchestrator_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "orchestrator", "SOUL JIRA.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("orchestrator_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_agent(
        model=model,
        tools=[
            deactivate_jira_mode,
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
        tools=[get_search_tool()],
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


async def coding_planner_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "coding_planner", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        tools=[handoff_from_planner_to_coder],
        system_prompt=soul,
        backend=backend,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "handoff_from_planner_to_coder": True,  # Review plan before handoff
                },
                description_prefix="Review implementation plan before handoff to coder",
            ),
        ],
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
        "results": [{"source": "coding_planner", "result": str(result["messages"][-1].content)}]
    }


async def coder_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "souls", "coder", "SOUL.md")
    storage_dir = os.path.join(base_dir, "project")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        tools=[write_file],
        system_prompt=soul,
        backend=backend,
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
    # tools = get_jira_toolkit().get_tools()
    agent = create_agent(
        model=model,
        tools=jira_tools,
        system_prompt=soul,
    )
    last_msg = state["messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [human_msg]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
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

def bridge(state: RouterState):
    return {"check_progress": ""}

def progress_router(state: RouterState):
    if state["check_progress"] == "NEXT_STEP":
        return "NEXT"
    elif state["check_progress"] == "END":
        return "END"

def check_mode(state: RouterState):
    keys = ["ticket_key", "project_key", "ticket_url"]
    if all(state.get(k) for k in keys):
        return "JIRA"
    else:
        return "GENERAL"

# Define the graph
builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("orchestrator", orchestrator_agent)
builder.add_node("orchestrator_jira", jira_mode_orchestrator_agent)
builder.add_node("researcher", researcher_agent)
builder.add_node("coding_planner", coding_planner_agent)
builder.add_node("coder", coder_agent)
builder.add_node("jira", jira_agent)
builder.add_node("evaluator", evaluator)
builder.add_node("bridge", bridge)
# builder.add_node("classifier", classify_query)
# builder.add_conditional_edges("classifier", route_to_agents, ["researcher", "coder"])


# Start with orchestrator
builder.add_conditional_edges(
    START,
    check_mode,
    {
        "JIRA": "orchestrator_jira",
        "GENERAL": "orchestrator"
    },
)
builder.add_edge("orchestrator", "evaluator")
builder.add_edge("orchestrator_jira", "evaluator")
builder.add_conditional_edges(
    "bridge",
    check_mode,
    {
        "JIRA": "orchestrator_jira",
        "GENERAL": "orchestrator"
    },
)
builder.add_conditional_edges(
    "evaluator",
    progress_router,
    {
        "NEXT": "bridge",
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