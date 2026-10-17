import asyncio
import random
from dotenv import load_dotenv
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver

# --- Test Configuration ---
# Choose which graph to test: "original" or "mainagent"
TEST_TARGET = "mainagent" 

if TEST_TARGET == "mainagent":
    from src.agent.mainagent import builder as agent_builder
    checkpointer = InMemorySaver()
    agent_graph = agent_builder.compile(checkpointer=checkpointer)
else:
    from src.agent.graph import builder as agent_builder
    checkpointer = InMemorySaver()
    agent_graph = agent_builder.compile(checkpointer=checkpointer)

load_dotenv()

config = {"configurable": {"thread_id": "test-multi-round-conversation"}}
result = {}
user_input=None

while True:
    if not result.get("interrupts", None):
        user_input = input("\nUser: ")
        if user_input.lower() in ["exit", "quit", "q"]:
            print("Ending conversation.")
            break
            
        if not user_input.strip():
            continue
    
    if result.get("interrupts", None):
        interrupt = result.get("interrupts", None)[0]
        action_request = interrupt.value['action_requests'][0]
        try:
            task = action_request['args']['task']
        except:
            task = action_request['args']

        print(f"\nPlan: {task}")
        user_input = input("Agree?: ")
        match user_input.lower():
            case "y":
                result = asyncio.run(agent_graph.ainvoke(
                    Command(
                        resume={"decisions": [{"type": "approve"}]}
                    ),
                    config=config, 
                    version="v2",
                ) )
                print(f"\nAssistant: {result['messages'][-1].content}")
            case "n":
                result = asyncio.run(agent_graph.ainvoke(
                    Command(
                        resume={"decisions": [{"type": "reject"}]} 
                    ),
                    config=config, 
                    version="v2",
                ) )
            case _:
                user_input = input("\nUser Respond: ")
                result = asyncio.run(agent_graph.ainvoke(
                    Command(
                        resume={"decisions": [{"type": "respond", "message": user_input}]} 
                    ),
                    config=config, 
                    version="v2",
                ) )
                print(f"\nAssistant: {result['messages'][-1].content}")
        
    else:
        result = asyncio.run(agent_graph.ainvoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
        ))
        if not result.get("interrupts", None):
            print(f"\nAssistant: {result['messages'][-1].content}")
