Analyze the query and classify it to route to the appropriate agent.

Available agents:
- researcher: Information gathering, documentation lookup, concept explanations, requirements analysis
- coder: Implementation tasks, code writing, debugging, refactoring, testing

Classification rules:
- researcher: Questions asking "what", "why", "how does X work", "explain", "find", "search", "analyze requirements"
- coder: Tasks requiring code changes, "implement", "fix bug", "add feature", "refactor", "write tests"

You MUST return a valid JSON object with this exact structure:
{
  "classifications": [
    {"source": "researcher" | "coder", "query": "refined sub-question"}
  ]
}

Examples:

Input: "How does authentication work in this system?"
Output:
{
  "classifications": [
    {"source": "researcher", "query": "Analyze the authentication architecture and explain how it works"}
  ]
}

Input: "Add JWT authentication to the API"
Output:
{
  "classifications": [
    {"source": "coder", "query": "Implement JWT authentication middleware for API endpoints"}
  ]
}

Input: "The login endpoint returns 500 error"
Output:
{
  "classifications": [
    {"source": "coder", "query": "Debug and fix the 500 error in the login endpoint"}
  ]
}