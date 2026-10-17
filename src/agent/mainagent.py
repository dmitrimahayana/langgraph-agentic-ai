import os, re
from pathlib import Path
from langgraph.graph import StateGraph, MessagesState, START, END
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
from deepagents import create_deep_agent
from typing_extensions import TypedDict
from langgraph.runtime import Runtime
from src.agent.model import ModelAgent
from src.agent.subagents import list_agents
from src.agent.catalog import catalog

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
SUBAGENT_MODEL = "ollama:gemma4:31b-cloud" 
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent.parent
PROFILE_DIR = PROJECT_ROOT / "profile"
WORK_DIR = str(PROJECT_ROOT / "workspace")

os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

class Context(TypedDict, total=False):
    orchestrator_model: str
    researcher_model: str
    coder_model: str

class RouterState(MessagesState):
    check_progress: str = ""

async def deepagents(state: RouterState, runtime: Runtime[Context]):
    # Use context model or default (context can be None)
    model_name = (runtime.context or {}).get("deepagents_model", DEFAULT_MODEL)
    model = ModelAgent(model_name=model_name).load_model()
    
    # Initialize a separate model for subagents
    subagent_model_name = (runtime.context or {}).get("subagent_model", SUBAGENT_MODEL)
    subagent_model = ModelAgent(model_name=subagent_model_name).load_model()
    
    # Pass the subagent-specific model to the loader
    subagents_list = list_agents(model=subagent_model)
    
    # Resolve Tavily tools from catalog
    tavily_tools = catalog.resolve(["tavily_search_results_json"])
    
    thinking = create_deep_agent(
        model=model,
        skills="src/agent/mainagent/skills/",
        backend=CompositeBackend(
            default=StateBackend(),
            routes={
                "/workspace/": FilesystemBackend(root_dir=WORK_DIR),
                "/skills/": FilesystemBackend(root_dir="src/agent/mainagent/skills/"),
            }),
        subagents=subagents_list,
        tools=tavily_tools
    )
    thinking_result = await thinking.ainvoke({"messages": state["messages"]})
    return {"messages": thinking_result["messages"]}

builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("deepagents", deepagents)

builder.add_edge(START, "deepagents")
builder.add_edge("deepagents", END)

graph = builder.compile()
