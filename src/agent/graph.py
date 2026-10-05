from __future__ import annotations
from typing import Any, Dict, Annotated
from langgraph.graph import StateGraph, MessagesState, START, END, add_messages
from langchain.tools import tool, ToolRuntime
from langgraph.runtime import Runtime
from typing_extensions import TypedDict
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
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
from langchain.messages import AnyMessage, HumanMessage, ToolMessage, AIMessage
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

config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "-y",
                    "@playwright/mcp@latest",
                    "--cdp-endpoint",
                    "http://localhost:9222"
                ],
            }
    }
}
browser_test = MCPAdapter(config)

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

class RouterState(MessagesState):
    """State that maintains conversation history via messages."""
    researcher_messages: Annotated[list[AnyMessage], add_messages]
    orchestrator_messages: Annotated[list[AnyMessage], add_messages]
    coder_messages: Annotated[list[AnyMessage], add_messages]
    jira_messages: Annotated[list[AnyMessage], add_messages]
    task_list: list = []
    current_task: str = ""
    check_progress: str = ""

class PlanStep(BaseModel):
    task: str
    expected_output: str

class ListPlanStep(BaseModel):
    plan: list[PlanStep]

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
    
@tool
def ask_user(prompt: str) -> str:
    """Ask the user a clarifying question when more information is needed."""
    # This function body is a placeholder. 
    # When intercepted by HITL, execution pauses before running this code.
    return prompt

@tool
def handoff_to_coder(task: str, runtime: ToolRuntime) -> Command:
    """Handle filesystem, writing code, reading code, open a file, list directory.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="coder",
        update={"coder_messages": [HumanMessage(f"Handed off to coder with task: {task}")]},
        graph=Command.PARENT,
    )
@tool
def ask_computer_agent(question: str, runtime: ToolRuntime) -> Command:
    """Ask Agent about current folder location, list directory, list of all file, open and read a file.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="think_coder",
        update={"coder_messages": [HumanMessage(f"question: {question}")]},
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
        update={"jira_messages": [HumanMessage(f"Handed off to jira with task: {task}")]},
        graph=Command.PARENT,
    )

@tool
def ask_jira_agent(question: str, runtime: ToolRuntime) -> Command:
    """Ask jira agent about ticket describtion, ticket status and tickte subtask.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    return Command(
        goto="think_jira",
        update={"jira_messages": [HumanMessage(f"question: {question}")]},
        graph=Command.PARENT,
    )

@tool
async def handoff_to_researcher_agent(task: str, runtime: ToolRuntime) -> Command:
    """Handle internet research and reference search tasks.
    Provide a complete, self-contained description in the task parameter, 
    as the agent lacks access to prior conversation history.
    """
    result = Command(
        goto="researcher",
        update={"researcher_messages": [HumanMessage(f"Handed off to researcher_agent with task: {task}")]},
        graph=Command.PARENT,
    )
    return result

@tool
async def report_issue_to_planner_agent(issue: str, runtime: ToolRuntime) -> Command:
    """Immedietly tell agent planner about current issue happening.
    Provide a complete, self-contained description in the plan parameter, 
    as the agent lacks access to prior conversation history.
    """
    result = Command(
        goto="planner",
        update={"messages":[AIMessage(f"Report issue from orchestrator with issue: {issue}")]},
        graph=Command.PARENT,
    )
    return result

@tool
async def handoff_to_orchestrator_planner_agent(plan: str, runtime: ToolRuntime) -> Command:
    """Delegate the complete plan to the orchestrator agent.
    Provide a complete, self-contained description in the plan parameter, 
    as the agent lacks access to prior conversation history.
    """
    result = Command(
        goto="planner_generator",
        update={},
        graph=Command.PARENT,
    )
    return result


async def create_plan_agent(state: RouterState, runtime: Runtime[Context]):
    # devide thingking and planning process
    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("planner_gen_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    planner = create_agent(
    model=model,
    system_prompt=""""generate step by step task plan. 
    Provide a complete, self-contained description of each plan, 
    as the other agent lacks access to prior conversation history""",
    response_format=ToolStrategy(
        schema=ListPlanStep,
        handle_errors=True # Catch validation errors and pass them back to the model for correction
    )   
    )
    planner_result = await planner.ainvoke({"messages": state["messages"]})
    print(planner_result["structured_response"])
    if planner_result.get("structured_response"):
        return Command(
            goto="orchestrator",
            update={
                "task_list": planner_result.get("structured_response").plan,
            }
        )
    else:
        return Command(
            goto="planner",
            update={
                "messages": state["messages"],
            }
        )


async def orchestrator_agent(state: RouterState, runtime: Runtime[Context]):
    file_path = os.path.join(base_dir, "souls", "orchestrator", "SOUL.md")
    soul = await read_md_file(file_path)
    model_name = (runtime.context or {}).get("orchestrator_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    if len(state.get("task_list", [])) > 0:
        next_task = state["task_list"].pop(0)
        # Use context model or default (context can be None)
        
        planstep = f"task :{next_task.task} \n expected output:{next_task.expected_output}"
        task = [state['messages'][-1]] + [HumanMessage(planstep)] + state['orchestrator_messages']
        
        agent = create_deep_agent(
            model=model,
            tools=[
                handoff_to_coder,
                handoff_to_jira_agent,
                handoff_to_researcher_agent,
                report_issue_to_planner_agent,
                ],
            system_prompt=soul,
        )
        result = await agent.ainvoke({"messages": task})

        if len(state.get("task_list", [])) > 0:
            return Command(
                goto="orchestrator",
                update={
                    "orchestrator_messages": result["messages"]
            })
        return Command(
            goto="planner",
            update={
                "messages": result["messages"][-1],
                "orchestrator_messages": result["messages"]
            }
        )
    else:
        agent = create_agent(
            model=model,
            system_prompt="sorry it seem there an error at planning step",
        )
        result = await agent.ainvoke({"messages": [{"role": "user", "content": "error plan step is not found"}]})
        return Command(
            goto="planner",
            update={"orchestrator_messages": result["messages"][-1], "messages": result["messages"][-1]}
        )

async def planner_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "planner", "SOUL.md")
    soul = await read_md_file(file_path)
    # devide thingking and planning process
    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("planner_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    thinking = create_agent(
        model=model,
        tools=[
            handoff_to_researcher_agent,
            handoff_to_orchestrator_planner_agent,
            ask_jira_agent,
            ask_computer_agent
        ],
        system_prompt=soul,
    )
    thinking_result = await thinking.ainvoke({"messages": state["messages"]})
    return Command(
        goto="bridge",
        update={
            "messages": thinking_result["messages"],
        }
    )

async def researcher_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "researcher", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("researcher_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    tools = await browser_test.list_tools()
    # tools = [search_tool]

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=soul,
    )
    last_msg = state["messages"][-1]
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state["researcher_messages"]})
    # Return results with source tracking
    return Command(
        goto="planner",
        update={
        "researcher_messages": result["messages"],
        "messages": result["messages"][-1]
        }
    )

async def coder_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "souls", "coder", "SOUL.md")
    soul = await read_md_file(file_path) + f"\n ###### The Current Folder Location is :{WORKDIR}"

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        system_prompt=soul,
        backend=backend_fl,
    )
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state.get("coder_messages",[])})
    # result["messages"] = [
    #     m for m in result["messages"] if not isinstance(m, HumanMessage)
    # ]
    # Return results with source tracking
    return Command(
        goto="orchestrator",
        update={
        "orchestrator_messages": result["messages"][-1],
        "coder_messages": result["messages"],
        "current_task": None
        }
    )

async def think_coder_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "souls", "coder", "SOUL.md")
    soul = await read_md_file(file_path) + f"\n ###### The Current Folder Location is :{WORKDIR}"

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("coder_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()

    agent = create_deep_agent(
        model=model,
        system_prompt=soul,
        backend=backend_fl,
    )
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state.get("coder_messages",[])})
    # Return results with source tracking
    return Command(
        goto="planner",
        update={
        "messages": result["messages"][-1],
        "coder_messages": result["messages"]
        }
    )

async def jira_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "jira", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("jira_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    agent = create_deep_agent(
        model=model,
        tools=jira_tools,
        system_prompt=soul,
    )
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state.get("jira_messages",[])})
    # result["messages"] = [
    #     m for m in result["messages"] if not isinstance(m, HumanMessage)
    # ]
    return Command(
        goto="orchestrator",
        update={
        "orchestrator_messages": result["messages"][-1],
        "jira_messages": result["messages"],
        "current_task": None
        }
    )

async def think_jira_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "jira", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("jira_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    agent = create_deep_agent(
        model=model,
        tools=jira_tools,
        system_prompt=soul,
    )
    # Invoke with conversation context - agent will see full message history
    result = await agent.ainvoke({"messages": state.get("jira_messages",[])})
    return Command(
        goto="planner",
        update={
        "jira_messages": result["messages"],
        "messages": result["messages"][-1]
        }
    )

def bridge(state: RouterState):
    return {"check_progress": ""}

# Define the graph
builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("planner_generator", create_plan_agent)
builder.add_node("orchestrator", orchestrator_agent)
builder.add_node("researcher", researcher_agent)
builder.add_node("planner", planner_agent)
builder.add_node("bridge", bridge)
builder.add_node("coder", coder_agent)
builder.add_node("think_coder", think_coder_agent)
builder.add_node("jira", jira_agent)
builder.add_node("think_jira", think_jira_agent)


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