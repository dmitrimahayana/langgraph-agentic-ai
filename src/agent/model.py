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

            # Auto-detect Ollama base URL
            # Priority: OLLAMA_BASE_URL env var > auto-detect Docker > localhost
            base_url = os.getenv("OLLAMA_BASE_URL")

            if not base_url:
                # Auto-detect: check if running in Docker
                if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
                    # Running in container - use host.docker.internal
                    base_url = "http://host.docker.internal:11434"
                    print("Detected Docker environment, using host.docker.internal")
                else:
                    # Running locally - use localhost
                    base_url = "http://localhost:11434"
                    print("Detected local environment, using localhost")

            return ChatOllama(
                model=new_model_name,
                base_url=base_url
            )
        else:
            raise ValueError("Unsupported model name")