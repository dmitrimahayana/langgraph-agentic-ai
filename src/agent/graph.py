from __future__ import annotations
from typing import Any, Dict, Annotated
from langgraph.graph import StateGraph, MessagesState, START, END, add_messages
from langchain.tools import tool, ToolRuntime
from langgraph.runtime import Runtime
from typing_extensions import TypedDict
from langchain.agents import create_agent
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.agent_toolkits.jira.toolkit import JiraToolkit
from langchain_community.utilities.jira import JiraAPIWrapper
from src.tools.jira.Jira import jira_tools
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.mcp import MCPAdapter
from deepagents.backends import StateBackend, FilesystemBackend, LocalShellBackend
from langchain.agents.middleware import HumanInTheLoopMiddleware 
from deepagents import create_deep_agent
from agent.model import ModelAgent
from langchain.messages import AnyMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from langgraph.types import Command
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
WORKDIR = os.path.abspath("./workspace_agent")
os.makedirs(WORKDIR, exist_ok=True)
jira_api = JiraAPIWrapper()
jira_toolkit = JiraToolkit.from_jira_api_wrapper(jira_api)
# client = SandboxClient()  # DEV: disabled to avoid quota
# ls_sandbox = client.create_sandbox()  # DEV: disabled to avoid quota
# backend = LangSmithSandbox(sandbox=ls_sandbox) # PROD
backend = StateBackend() # DEV
backend_fl = FilesystemBackend(root_dir=WORKDIR)
# backend_shell = LocalShellBackend(
#     root_dir=WORKDIR,
#     # Pass an explicit, minimal PATH instead of inheriting your full env.
#     env={"PATH": "/usr/bin:/bin"},
# ) # DEV 2 very risky be carefull!! check if HITL is activated

# Lazy initialization for search tool - requires TAVILY_API_KEY env var
# search_tool = DuckDuckGoSearchRun()
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

# disabled, causing bugs
# _jira_toolkit = None
# def get_jira_toolkit():
#     global _jira_toolkit
#     if _jira_toolkit is None:
#         jira_api = JiraAPIWrapper()
#         _jira_toolkit = JiraToolkit.from_jira_api_wrapper(jira_api)
#     return _jira_toolkit

# config = {
#         "mcpServers": {
#             "playwright": {
#                 "command": "npx",
#                 "args": [
#                     "-y",
#                     "@playwright/mcp@latest",
#                     "--cdp-endpoint",
#                     "http://localhost:9222"
#                 ],
#             }
#     }
# }
# browser_test = MCPAdapter(config)

async def read_md_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

class Context(TypedDict, total=False):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """
    orchestrator_model: str  # e.g., "ollama:gemma4:31b-cloud"
    researcher_model: str
    coder_model: str

class AgentOutput(TypedDict):
    """Output from each subagent."""
    source: str
    result: str

class RouterState(MessagesState):
    """State that maintains conversation history via messages."""
    specialist_messages: Annotated[list[AnyMessage], add_messages]
    check_progress: str
    results: Annotated[list[AgentOutput], operator.add]  # Reducer collects parallel results


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

# @tool
# def handoff_to_coder_agent(task: str, runtime: ToolRuntime) -> Command:
#     """Delegate coding and filesystem tasks to the coder agent.
#     Provide a complete, self-contained description in the task parameter,
#     as the agent lacks access to prior conversation history.
#     """
#     return Command(
#         goto="coding_planner",
#         update={"messages": [ToolMessage(
#             content=f"Handed off to coding planner with task: {task}",
#             tool_call_id=runtime.tool_call_id,
#         )]},
#         graph=Command.PARENT,
#     )
    
@tool
def ask_user(prompt: str) -> str:
    """Ask the user a clarifying question when more information is needed."""
    # This function body is a placeholder. 
    # When intercepted by HITL, execution pauses before running this code.
    return prompt

@tool
def handoff_to_coder(task: str, runtime: ToolRuntime) -> Command:
    """Hand off to coder agent with implementation task.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="coder",
        update={"specialist_messages": [ToolMessage(
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
        update={"specialist_messages": [ToolMessage(
            content=f"Handed off to jira with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )

@tool
async def handoff_to_planner(output_task: str, runtime: ToolRuntime) -> Command:
    """Delegate planning and evaluating task to planning agent.
    this agent would plan and evaluate your work result
    Provide a complete, self-contained description in the output_task parameter.
    """
    result = Command(
        goto="planner",
        update={"messages": [ToolMessage(
            content=f"Handed off to planner_agent with task: {output_task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )
    return result

@tool
async def handoff_to_researcher_agent(task: str, runtime: ToolRuntime) -> Command:
    """Delegate internet research and reference tasks to the researcher agent.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    result = Command(
        goto="researcher",
        update={"messages": [ToolMessage(
            content=f"Handed off to researcher_agent with task: {task}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )
    return result

@tool
async def handoff_to_orchestrator_agent(plan: str, runtime: ToolRuntime) -> Command:
    """Delegate plan for execution to the orchestrator agent.
    Provide a complete, self-contained description in the plan parameter, 
    as the agent lacks access to prior conversation history.
    """
    result = Command(
        goto="orchestrator",
        update={"messages": [ToolMessage(
            content=f"Handed off to orchestrator_agent with plan: {plan}",
            tool_call_id=runtime.tool_call_id,
        )]},
        graph=Command.PARENT,
    )
    return result

async def orchestrator_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "orchestrator", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("orchestrator_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    last_msg = state["messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    full_state =  [human_msg] + state["specialist_messages"]
    
    agent = create_deep_agent(
        model=model,
        tools=[
            handoff_to_coder,
            handoff_to_jira_agent
            ],
        system_prompt=soul,
    )
    result = await agent.ainvoke({"messages": full_state})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
    return Command(
        goto="planner",
        update={"messages": result["messages"]}
    )

async def planner_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "planner", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("orchestrator_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    agent = create_agent(
        model=model,
        tools=[
            handoff_to_researcher_agent,
            handoff_to_orchestrator_agent
        ],
        system_prompt=soul
    )
    result = await agent.ainvoke({"messages": state["messages"]})
    return Command(
        goto="bridge",
        update={"messages": result["messages"]}
    )


async def researcher_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "researcher", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("researcher_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    # tools = await browser_test.list_tools()

    agent = create_deep_agent(
        model=model,
        tools=[get_search_tool()],
        system_prompt=soul,
    )
    last_msg = state["messages"][-1]
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [{"role": "user", "content": last_msg.content}]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
    # Return results with source tracking
    return Command(
        goto="planner",
        update={
        "messages": result["messages"],
        "results": [{"source": "researcher", "result": str(result["messages"][-1].content)}]
        }
    )

async def coder_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "souls", "coder", "SOUL.md")
    soul = await read_md_file(file_path) + f"\n #### current folder location is :{WORKDIR}"

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        system_prompt=soul,
        backend=backend_fl,
        # middleware=[
        #     HumanInTheLoopMiddleware(
        #         interrupt_on={
        #             "execute": {
        #                 "allowed_decisions": ["approve", "respond", "reject"]
        #             },
        #         },
        #         description_prefix="review shell execution before running it",
        #     ),
        # ],
    )
    last_msg = state["specialist_messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [human_msg]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
    # Return results with source tracking
    return Command(
        goto="orchestrator",
        update={
        "specialist_messages": result["messages"]
        }
    )

async def jira_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "jira", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("jira_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    tools = jira_toolkit.get_tools()
    agent = create_deep_agent(
        model=model,
        tools=jira_tools,
        system_prompt=soul,
    )
    last_msg = state["specialist_messages"][-1]
    human_msg = HumanMessage(content=last_msg.content)
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": [human_msg]})
    result["messages"] = [
        m for m in result["messages"] if not isinstance(m, HumanMessage)
    ]
    return Command(
        goto="orchestrator",
        update={
        "specialist_messages": result["messages"]
        }
    )

def bridge(state: RouterState):
    return {"check_progress": ""}

# Define the graph
builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("orchestrator", orchestrator_agent)
builder.add_node("researcher", researcher_agent)
builder.add_node("planner", planner_agent)
builder.add_node("bridge", bridge)
# builder.add_node("coding_planner", coding_planner_agent)
builder.add_node("coder", coder_agent)
builder.add_node("jira", jira_agent)
# builder.add_node("evaluator", evaluator)
# builder.add_node("classifier", classify_query)
# builder.add_conditional_edges("classifier", route_to_agents, ["researcher", "coder"])


# Start with orchestrator
builder.add_edge(START, "planner")
builder.add_edge("bridge", END)
# builder.add_conditional_edges(
#     START,
#     check_mode,
#     {
#         "JIRA": "orchestrator_jira",
#         "GENERAL": "orchestrator"
#     },
# )
# builder.add_edge("orchestrator_jira", "evaluator")
# builder.add_conditional_edges(
#     "bridge",
#     check_mode,
#     {
#         "JIRA": "orchestrator_jira",
#         "GENERAL": "orchestrator"
#     },
# )
# builder.add_conditional_edges(
#     "evaluator",
#     progress_router,
#     {
#         "NEXT": "bridge",
#         "END": END
#     },
# )

# After specialist agents complete, go to END
# builder.add_edge("researcher", END)
# builder.add_edge("coder", END)

# LangGraph API provides persistence automatically
# - langgraph dev: in-memory checkpointer
# - production deploy: PostgreSQL checkpointer (uses POSTGRES_URI from .env)
graph = builder.compile()