import asyncio
from dotenv import load_dotenv
load_dotenv()
from src.agent.graph import graph

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
    
    # Print the latest response from the graph
    latest_message = result["messages"][-1]
    print(f"\nAssistant: {latest_message.content}")