from langgraph.graph import StateGraph, MessagesState, START, END, add_messages
from deepagents import create_deep_agent
from typing_extensions import TypedDict
from langgraph.runtime import Runtime
from agent.model import ModelAgent

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"

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
        tools=[],
        system_prompt=,
    )
    thinking_result = await thinking.ainvoke({"messages": state["messages"]})

builder = StateGraph(RouterState, context_schema=Context)
builder.add_node("deepagents", deepagents)

builder.add_edge(START, "deepagents")
builder.add_edge("deepagents", END)

graph = builder.compile()