from fastapi import FastAPI
from pydantic import BaseModel
from gliner2 import AutoExtractor

app = FastAPI()
# This loads the model locally, just like Ollama pulls a model
model = AutoExtractor.from_pretrained("fastino/GLiNER2.5-Decide")

class DecisionRequest(BaseModel):
    text: str
    labels: list[str]

@app.post("/v1/decide")
def decide(data: DecisionRequest):
    # This evaluates the task in a fast, single forward pass
    result = model.extract_entities(data.text, data.labels)
    return {"result": result}

# --- Standard Python Entry Point ---
if __name__ == "__main__":
    import uvicorn
    # This replaces the external uvicorn CLI command
    uvicorn.run("glide:app", host="127.0.0.1", port=8000)
