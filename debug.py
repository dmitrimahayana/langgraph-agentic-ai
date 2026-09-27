import asyncio
import random
from dotenv import load_dotenv
from src.agent.graph import graph, builder
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver


load_dotenv()
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "test-multi-round-conversation"}}

while True:
    # user_input = input("\nUser: ")
    language_programming = ["Python", "JavaScript", "Java", "C++", "C#", "Ruby", "Go", "Swift", "Kotlin", "PHP", "TypeScript", "Rust", "Scala", "Perl", "Haskell", "Lua", "Objective-C", "R", "Dart", "Elixir"]
    user_input = f"write a quick sort in {random.choice(language_programming)} and name it test_sort"
    print(f"\nHuman: {user_input}")
    if user_input.lower() in ["exit", "quit", "q"]:
        print("Ending conversation.")
        break
        
    if not user_input.strip():
        continue
    
    
    result = asyncio.run(graph.ainvoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
    ))
    print(f"\nAssistant: {result['messages'][-1].content}")
    if "__interrupt__" in result:
        interrupt = result['__interrupt__'][0]
        action_request = interrupt.value['action_requests'][0]
        task = action_request['args']['task']
        print(f"\nPlan: {task}")
        user_input = input("Agree?: ")
        match user_input.lower():
            case "y":
                result = asyncio.run(graph.ainvoke(
                    Command(
                        resume={"decisions": [{"type": "approve"}]}
                    ),
                    config=config, # Same thread ID to resume the paused conversation
                    version="v2",
                ) )
            case "n":
                result = asyncio.run(graph.ainvoke(
                    Command(
                        resume={"decisions": [{"type": "reject"}]} 
                    ),
                    config=config, # Same thread ID to resume the paused conversation
                    version="v2",
                ) )
            case _:
                user_input = input("\nUser Respond: ")
                result = asyncio.run(graph.ainvoke(
                    Command(
                        resume={"decisions": [{"type": "respond", "message": user_input}]} 
                    ),
                    config=config, # Same thread ID to resume the paused conversation
                    version="v2",
                ) )

        # Print the latest response from the graph
        latest_message = result["messages"][-1]
        print(f"\nAssistant: {latest_message.content}")