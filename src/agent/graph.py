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
from langchain_community.agent_toolkits.jira.toolkit import JiraToolkit
from langchain_community.utilities.jira import JiraAPIWrapper
from deepagents.backends import StateBackend, FilesystemBackend
from langchain.agents.middleware import HumanInTheLoopMiddleware 
from deepagents import create_deep_agent
from agent.model import ModelAgent
from langchain.messages import ToolMessage, HumanMessage
from pydantic import BaseModel, Field
from langgraph.types import Command
from langsmith.sandbox import SandboxClient
from deepagents.backends import LangSmithSandbox
from typesafe_sdk import Choice, Noul, Score, AsyncTypeSafeClient
from langchain_core.tools import StructuredTool
import operator
import json
import os

# Send(): Jump/Delegate
# Directly transitions execution to the target node and continues along 
# the new graph path. Does not return to the caller node.

# Command(): Invoke & Return
# Calls a specific node like a subroutine and returns back to the caller 
# once finished. The invoked node can directly alter/update the State. the caller then read the altered State

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
TYPESAFE_AI_API_KEY = os.environ.get("TYPESAFE_AI_API_KEY", None)
base_dir = os.path.dirname(os.path.abspath(__file__))
# Coder may only touch files inside this folder (see souls/coder/SOUL.md)
# Coder output lives outside the repo so `langgraph dev` hot reload is not triggered
SCRIPT_DIR = os.path.expanduser(os.environ.get("CODER_WORKSPACE_DIR", "~/agent-workspace"))
# client = SandboxClient()  # DEV: disabled to avoid quota
# ls_sandbox = client.create_sandbox()  # DEV: disabled to avoid quota
# backend = LangSmithSandbox(sandbox=ls_sandbox) # PROD
backend = StateBackend() # DEV
CONFIDENCE_THRESHOLD = 0.6
Route = Literal["coder", "researcher", "admin", "orchestrator"]
# Classifier label -> graph node
AGENT_NODES: dict[str, Route] = {
    "coder": "coder",
    "researcher": "researcher",
    "admin": "admin",
}

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
_jira_tools = None
def get_jira_tools():
    """Jira tools wrapped so dict args from tool-calling models are JSON-encoded.

    JiraAPIWrapper calls json.loads() on the raw instructions, which fails
    when the model sends a JSON object instead of a JSON string.
    """
    global _jira_tools
    if _jira_tools is None:
        jira_api = JiraAPIWrapper()
        toolkit = JiraToolkit.from_jira_api_wrapper(jira_api)

        def wrap(jira_tool):
            def _run(instructions: str | dict) -> str:
                if not isinstance(instructions, str):
                    instructions = json.dumps(instructions)
                try:
                    return jira_tool.api_wrapper.run(jira_tool.mode, instructions)
                except AttributeError as e:
                    # "other" mode does getattr(jira, function); model guessed a bad name
                    return f"Error: {e}. Use a valid atlassian-python-api Jira method name."
                except Exception as e:
                    # Let the model see the error and retry instead of crashing the graph
                    return f"Error: {type(e).__name__}: {e}"

            description = jira_tool.description
            if jira_tool.mode == "other":
                description += (
                    "\nTo change issue status use "
                    '{"function": "set_issue_status", "args": ["PROJ-1", "In Progress"]}. '
                    'List available transitions with {"function": "get_issue_transitions", "args": ["PROJ-1"]}.'
                )

            return StructuredTool.from_function(
                func=_run,
                name=jira_tool.name,
                description=description,
            )

        _jira_tools = [wrap(t) for t in toolkit.get_tools()]
    return _jira_tools


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
    source: Literal["researcher", "coder", "admin"]
    query: str
    confidence: float


class AgentOutput(TypedDict):
    """Output from each subagent."""
    source: str
    result: str


class RouterState(MessagesState):
    """State that maintains conversation history via messages."""
    classifications: Annotated[list[Classification], operator.add]  # Routing history across turns
    check_progress: str
    agent_name: str
    agent_confidence: float
    agent_probability: dict[str, float]
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results


# Define structured output schema for the classifier
class ClassificationResult(BaseModel):
    """Result of classifying a user query into agent-specific sub-questions."""
    classifications: list[Classification] = Field(
        description="List of agents to invoke with their targeted sub-questions"
    )

# File system tools
def resolve_script_path(file_path: str) -> str | None:
    """Resolve file_path inside SCRIPT_DIR, or None if it points outside it.

    Accepts absolute paths, ~-prefixed paths, or paths relative to SCRIPT_DIR.
    """
    path = os.path.expanduser(file_path.replace("\\", "/"))
    if not os.path.isabs(path):
        path = os.path.join(SCRIPT_DIR, path.lstrip("/"))
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(SCRIPT_DIR)
    if os.path.commonpath([real_path, real_root]) != real_root:
        return None
    return real_path


@tool
def save_script_file(file_path: str, content: str) -> str:
    """Write content to a file inside the coder workspace (~/agent-workspace).

    Args:
        file_path: Path of the file, relative to the coder workspace
        content: The content to write to the file

    Returns:
        Success message with file path, or an error if the path is outside the coder workspace
    """
    resolved = resolve_script_path(file_path)
    if resolved is None:
        return f"Error: {file_path} is outside {SCRIPT_DIR}. The coder may only write files inside {SCRIPT_DIR}."
    file_path = resolved
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
        goto="admin",
        update={"messages": [ToolMessage(
            content=f"Handed off to jira with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )


async def read_md_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def classify_query(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    last_message = state["messages"][-1]
    typesafe_client = AsyncTypeSafeClient(api_key=TYPESAFE_AI_API_KEY)
    response = await typesafe_client.system_one(
        state=last_message.content,
        questions={
            "agent_name": Choice(
                instructions="Which team should handle this",
                criteria={
                    "coder": "write, edit, debug or save code and files",
                    "researcher": "explain, look up, compare or research a topic on the internet",
                    "admin": "Jira tickets, issues, FAQ, project administration",
                },
            ),
        },
    )
    agent_choice = response.answers["agent_name"]
    print(f"typesafe classification: {agent_choice.choice} (confidence: {agent_choice.confidence}) probabilities: {agent_choice.probabilities}")
    return {
        "classifications": [{
            "source": AGENT_NODES.get(agent_choice.choice, agent_choice.choice),
            "query": last_message.content,
            "confidence": agent_choice.confidence,
        }],
        "agent_name": agent_choice.choice,
        "agent_confidence": agent_choice.confidence,
        "agent_probability": agent_choice.probabilities,
    }


def route_by_agent(state: RouterState) -> Route:
    # Unsure -> LLM orchestrator clarifies or decides
    if state.get("agent_confidence", 0) < CONFIDENCE_THRESHOLD:
        return "orchestrator"
    return AGENT_NODES.get(state.get("agent_name", ""), "orchestrator")


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


async def coder_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "coder", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        tools=[save_script_file],
        system_prompt=soul,
        backend=backend,
    )
    # Pass full history so follow-ups can resolve earlier context
    history = state["messages"]
    result = await agent.ainvoke({"messages": history})
    seen_ids = {m.id for m in history}
    new_messages = [m for m in result["messages"] if m.id not in seen_ids]
    # Return results with source tracking
    return {
        "messages": new_messages,
        "results": [{"source": "coder", "result": str(new_messages[-1].content)}]
    }

async def admin_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "admin", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("admin_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    tools = get_jira_tools()

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=soul,
    )
    # Pass full history so follow-ups ("last ticket") can resolve earlier context
    history = state["messages"]
    result = await agent.ainvoke({"messages": history})
    seen_ids = {m.id for m in history}
    new_messages = [m for m in result["messages"] if m.id not in seen_ids]
    # Return results with source tracking
    return {
        "messages": new_messages,
        "results": [{"source": "admin", "result": str(new_messages[-1].content)}]
    }


# Define the graph
builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("classify_query", classify_query)
builder.add_node("orchestrator", orchestrator_agent)
builder.add_node("researcher", researcher_agent)
# builder.add_node("coding_planner", coding_planner_agent)
builder.add_node("coder", coder_agent)
builder.add_node("admin", admin_agent)

# Classify first; orchestrator LLM only as low-confidence fallback
builder.add_edge(START, "classify_query")
builder.add_conditional_edges(
    "classify_query",
    route_by_agent,
    ["coder", "researcher", "admin", "orchestrator"],
)
builder.add_edge("researcher", END)
builder.add_edge("coder", END)
builder.add_edge("admin", END)

# LangGraph API provides persistence automatically
# - langgraph dev: in-memory checkpointer
# - production deploy: PostgreSQL checkpointer (uses POSTGRES_URI from .env)
graph = builder.compile()