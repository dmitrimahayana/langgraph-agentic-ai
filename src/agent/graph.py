from __future__ import annotations
from typing import Any, Dict, Annotated
from langgraph.graph import StateGraph, MessagesState, START, END, add_messages
from langchain.tools import tool, ToolRuntime
from langgraph.runtime import Runtime
from typing_extensions import TypedDict
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from src.tools.jira.Jira import jira_tools
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.mcp import MCPAdapter
from deepagents.backends import StateBackend, FilesystemBackend, LocalShellBackend
from typesafe_sdk import Choice, Noul, Score, AsyncTypeSafeClient
from langchain.agents.middleware import HumanInTheLoopMiddleware 
from deepagents import create_deep_agent
from agent.model import ModelAgent
from langchain.messages import AnyMessage, HumanMessage, ToolMessage, AIMessage
from pydantic import BaseModel, Field
from langgraph.types import Command
import os
from dotenv import load_dotenv

load_dotenv()
# Send(): Jump/Delegate
# Directly transitions execution to the target node and continues along 
# the new graph path. Does not return to the caller node.

# Command(): Invoke & Return
# Calls a specific node like a subroutine and returns back to the caller 
# once finished. The invoked node can directly alter/update the State. the caller then read the altered State
TYPESAFE_AI_API_KEY = os.getenv("TYPESAFE_AI_API_KEY")
DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
base_dir = os.path.dirname(os.path.abspath(__file__))
WORKDIR = os.path.abspath("./workspace_agent")
os.makedirs(WORKDIR, exist_ok=True)
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
async def handoff_to_orchestrator(task: str, runtime: ToolRuntime) -> Command:
    """Delegate the task step to the orchestrator agent. 
    Provide a complete, self-contained description in the plan parameter, 
    as the agent does not have access to the previous conversation history.
    """
    result = Command(
        goto="router",
        update={},
        graph=Command.PARENT,
    )
    return result

async def research_think_agent(state: RouterState, runtime: Runtime[Context]) -> Dict[str, Any]:
    file_path = os.path.join(base_dir, "souls", "planner", "SOUL.md")
    soul = await read_md_file(file_path)

    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("planner_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    thinking = create_agent(
        model=model,
        tools=[
            get_search_tool(),
            handoff_to_orchestrator,
            ask_jira_agent,
            ask_computer_agent,
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
builder.add_node("research_think_agent", research_think_agent)
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