from langchain_ollama import ChatOllama

class ModelAgent:
    """A simple agent that uses the Ollama model for chat."""

    def __init__(self, model_name: str = "ollama:gemma4:31b-cloud"):
        self.model_name = model_name
        

    def load_model(self):
        if self.model_name.startswith("ollama:"):
            new_model_name = self.model_name.split("ollama:")[1]
            print(f"Loading Ollama model: {new_model_name}")
            return ChatOllama(model=new_model_name)
        else:
            raise ValueError("Unsupported model name")