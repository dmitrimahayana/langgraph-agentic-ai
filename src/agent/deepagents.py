import os
from langgraph.graph import StateGraph, MessagesState, START, END
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
from deepagents import create_deep_agent
from typing_extensions import TypedDict
from langgraph.runtime import Runtime
from agent.model import ModelAgent

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKDIR = os.path.abspath("./workspace_agent")
MEMORIES = os.path.abspath("./memories")
os.makedirs(WORKDIR, exist_ok=True)
os.makedirs(MEMORIES, exist_ok=True)

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
                WORKDIR: FilesystemBackend(root_dir=WORKDIR),
        })
    )
    thinking_result = await thinking.ainvoke({"messages": state["messages"]})
    return {"messages": thinking_result["messages"]}

builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("deepagents", deepagents)

builder.add_edge(START, "deepagents")
builder.add_edge("deepagents", END)

graph = builder.compile()