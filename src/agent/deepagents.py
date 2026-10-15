import os, re
from langgraph.graph import StateGraph, MessagesState, START, END
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
from deepagents import create_deep_agent
from typing_extensions import TypedDict
from langgraph.runtime import Runtime
from agent.model import ModelAgent

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = BASE_DIR / "profile"
WORK_DIR = os.path.abspath("./workspace_agent")
MEMORIES_DIR = os.path.abspath("./memories")
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(MEMORIES_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

def agents_dir():
    """Root folder holding agent folders."""
    return PROFILE_DIR
    
def list_agents() -> list:
    root = agents_dir()
    specs = []
    for path in sorted(root.iterdir()) if root.is_dir() else []:
        if path.is_dir() and NAME_RE.match(path.name) and is_agent_dir(path):
            try:
                specs.append(load_agent(path))
            except Exception as e:
                print("Skipping agent folder %s: %s", path, e)
    return specs


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
    thinking = create_deep_agent(
        model=model,
        backend=[],
        skills="src/agent/core/deepagents/skills/",
        backend=CompositeBackend(
            default=StateBackend(),
            routes={
                WORK_DIR: FilesystemBackend(root_dir=WORK_DIR),
        })
    )
    thinking_result = await thinking.ainvoke({"messages": state["messages"]})
    return {"messages": thinking_result["messages"]}

builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("deepagents", deepagents)

builder.add_edge(START, "deepagents")
builder.add_edge("deepagents", END)

graph = builder.compile()