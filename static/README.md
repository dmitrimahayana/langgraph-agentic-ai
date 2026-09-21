# LangGraph Frontend

Simple web UI for your LangGraph multi-agent system.

## Quick Start

1. **Start LangGraph Server:**
   ```bash
   langgraph up
   ```
   Server starts at `http://localhost:8123`

2. **Start Frontend Server (with CORS proxy):**
   ```bash
   cd static
   python server.py
   ```
   Then open `http://localhost:8080`

## Configuration Options

In the UI, you can configure:

- **API URL**: 
  - `/api` - Uses proxy server (recommended, avoids CORS)
  - `http://localhost:8123` - Direct connection (requires CORS workaround)
  
- **Assistant**: Name of your assistant (default: `agent`)
  - Check available assistants: `curl -X POST http://localhost:8123/assistants/search -H "Content-Type: application/json" -d '{"limit": 10}'`

- **Thread ID**: Auto-generated or specify your own for conversation persistence

## Alternative: Direct Connection (CORS issues)

If you want to connect directly to LangGraph API without the proxy:

1. Change API URL in the UI to `http://localhost:8123`
2. Open in Chrome with CORS disabled:
   ```bash
   open -na "Google Chrome" --args --disable-web-security --user-data-dir=/tmp/chrome-cors
   ```
   ⚠️ Only for testing - not safe for browsing!

## API Endpoints Used

- `POST /threads/{thread_id}/runs/stream` - Stream chat responses
  - Body: `{"assistant_id": "agent", "input": {"messages": [...]}, "stream_mode": "messages"}`
  
See full API docs at: http://localhost:8123/docs

## Features

- Clean chat interface
- Streaming responses from LangGraph API
- Multi-agent system (orchestrator → researcher/coder)
- Thread management for conversation persistence
- Configurable API endpoint

## API Endpoints Used

- `POST /threads/{thread_id}/runs/stream` - Stream chat responses
- Assistant ID: `default` (configured in langgraph.json)

## Architecture

Your LangGraph agent:
- **Orchestrator**: Routes tasks to specialized agents
- **Researcher**: Web search via Tavily
- **Coder**: Code execution in sandbox

The frontend sends messages to the orchestrator, which delegates to the appropriate agent.

## Development

To customize:
- Edit `index.html` for UI changes
- API config in `langgraph.json`
- Agent logic in `src/agent/graph.py`
