from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
import os

TYPESAFE_AI_API_KEY = os.environ.get("TYPESAFE_AI_API_KEY", None)
typesafe_client = TypeSafeClient(api_key=TYPESAFE_AI_API_KEY)
response = typesafe_client.system_one(
        state="update ticket #54321 to 'in progress' and assign it to the coder team",
        questions={
            "agent_name": Choice(
                instructions="Which team should handle this",
                criteria={
                    "coder": "coding, development",
                    "researcher": "analysis, deep thinking, complex logic",
                    "admin": "faq, ticketing"
                },
            ),
        }
    )
print(response.answers["agent_name"])  # Output: coder
agent_choice =response.answers["agent_name"]
status = {
    "agent_name": agent_choice.choice,
    "agent_confidence": agent_choice.confidence,
    "agent_probability": agent_choice.probabilities
}
print(status)