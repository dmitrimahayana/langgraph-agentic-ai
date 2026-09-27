#!/bin/bash
# Start the LangGraph frontend server

cd "$(dirname "$0")/static"

echo "Starting LangGraph Frontend..."
echo ""
echo "Make sure LangGraph is running:"
echo "  langgraph up"
echo ""

python3 server.py
