import asyncio
from dotenv import load_dotenv
load_dotenv()
from src.agent.graph import graph
from langgraph.types import Command

config = {"configurable": {"thread_id": "test-multi-round-conversation"}}
    
while True:
    user_input = input("\nUser: ")
    if user_input.lower() in ["exit", "quit", "q"]:
        print("Ending conversation.")
        break
        
    if not user_input.strip():
        continue
    
    
    result = asyncio.run(graph.ainvoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
    ))
    if "__interrupt__" in result:
        print(result["__interrupt__"])
    user_input = input("Agree?: ")
    if user_input.lower() in ["y"]:
        result = asyncio.run(graph.ainvoke(
            Command(
                resume={"decisions": [{"type": "approve"}]}  # or "reject"
            ),
            config=config, # Same thread ID to resume the paused conversation
            version="v2",
        ) )

    # Print the latest response from the graph
    latest_message = result["messages"][-1]
    print(f"\nAssistant: {latest_message.content}")