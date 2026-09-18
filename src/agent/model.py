import os
from langchain_ollama import ChatOllama

class ModelAgent:
    """A simple agent that uses the Ollama model for chat."""

    def __init__(self, model_name: str = "ollama:gemma4:31b-cloud"):
        self.model_name = model_name


    def load_model(self):
        if self.model_name.startswith("ollama:"):
            new_model_name = self.model_name.split("ollama:")[1]
            print(f"Loading Ollama model: {new_model_name}")

            # Get Ollama base URL from env (for Docker: host.docker.internal:11434)
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

            return ChatOllama(
                model=new_model_name,
                base_url=base_url
            )
        else:
            raise ValueError("Unsupported model name")