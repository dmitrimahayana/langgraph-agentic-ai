# Test Suite

Comprehensive test coverage for the multi-agent orchestration system.

## Test Structure

```
tests/
├── conftest.py                          # Shared fixtures
├── unit_tests/
│   ├── test_configuration.py            # Graph structure tests
│   ├── test_orchestrator.py             # Orchestrator agent tests
│   ├── test_classifier.py               # Classifier/router tests
│   └── test_agents.py                   # Researcher & coder agent tests
└── integration_tests/
    ├── test_graph.py                    # Basic integration tests
    └── test_agent_flows.py              # Full workflow tests
```

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Unit Tests Only
```bash
pytest tests/unit_tests/
```

### Run Integration Tests Only
```bash
pytest tests/integration_tests/
```

### Run Specific Test File
```bash
pytest tests/unit_tests/test_orchestrator.py
```

### Run with Coverage
```bash
pytest --cov=agent --cov-report=html
```

### Run Verbose
```bash
pytest -v
```

## Test Categories

### Unit Tests

#### `test_configuration.py`
- Graph compilation validation
- Node structure verification
- Context schema validation

#### `test_orchestrator.py`
Tests for orchestrator agent behavior:

**Clear Queries:**
- Clear research query handling
- Clear coding query handling

**Ambiguous Queries:**
- Vague improvement requests
- Requests needing clarification

**Follow-up Queries:**
- Context maintenance across turns
- Reference to previous conversation

**Configuration:**
- Custom model usage
- Default model fallback

#### `test_classifier.py`
Tests for classifier/router logic:

**Clear Query Routing:**
- Research queries → researcher
- Coding queries → coder
- Bug fixes → coder

**Explain vs Implement:**
- "Explain how to X" → researcher
- "Implement X" → coder
- "How does X work" → researcher

**Follow-up Context:**
- Context-aware routing
- Message history consideration

**Structured Output:**
- Valid JSON classification format
- Source validation (researcher/coder)

#### `test_agents.py`
Tests for individual specialist agents:

**Researcher Agent:**
- Message processing
- Search tool access
- Conversation context maintenance

**Coder Agent:**
- Code generation
- Debugging tasks
- Context maintenance

**Configuration:**
- Custom model usage
- Default fallback behavior

### Integration Tests

#### `test_graph.py`
Basic integration tests:
- Agent responds to messages
- Memory within thread
- Thread isolation (no crosstalk)

#### `test_agent_flows.py`
Full workflow integration tests:

**Clear Query Flows:**
- `orchestrator → classifier → researcher`
- `orchestrator → classifier → coder`
- Bug fix workflows

**Ambiguous Query Flows:**
- Clarification requests
- Vague query handling

**Follow-up Query Flows:**
- Research → implement pattern
- Debugging multi-step workflow
- Context maintained across turns

**Explain vs Implement:**
- "Can you tell me how to create X" → researcher
- "Create X" → coder
- "How does X work" → researcher

**Thread Isolation:**
- Different threads don't share context
- Conversation history isolated per thread

## Test Use Cases

### Clear Queries

**Research Example:**
```python
User: "Explain how bubble sort algorithm works"
Flow: orchestrator → classifier → researcher
Expected: Explanation of bubble sort
```

**Coding Example:**
```python
User: "Implement bubble sort in Python"
Flow: orchestrator → classifier → coder
Expected: Python code implementation
```

### Ambiguous Queries

**Improvement Request:**
```python
User: "Improve the authentication system"
Flow: orchestrator asks: "research or coding?"
Expected: Clarification request
```

**Vague Request:**
```python
User: "Fix the app"
Flow: orchestrator asks: "what's broken?"
Expected: Request for details
```

### Follow-up Queries

**Research → Implement:**
```python
Turn 1: "Explain JWT authentication" → researcher
Turn 2: "Now implement it" → coder
Expected: Context flows, coder implements based on explanation
```

**Debugging Workflow:**
```python
Turn 1: "Login returns 500 error" → coder
Turn 2: "What caused it?" → researcher
Turn 3: "Fix it" → coder
Expected: Context maintained, appropriate routing each turn
```

## Key Test Scenarios

### 1. "Explain How to X" vs "Implement X"

This distinction is critical:

```python
# Goes to researcher (wants explanation)
"Can you tell me how to create logic bubble sort in C++?"

# Goes to coder (wants code)
"Create a bubble sort function in C++"
```

Tests verify classifier correctly routes based on intent.

### 2. Conversation Context

All agents should maintain conversation history:

```python
Turn 1: "What is authentication?"
Turn 2: "What about JWT specifically?"  # References previous context
Turn 3: "Implement it in our API"       # References JWT from earlier
```

Tests verify messages flow through all nodes.

### 3. Thread Isolation

Different threads should not share state:

```python
Thread A: "Explain JWT" → discusses authentication
Thread B: "Implement bubble sort" → should NOT know about JWT
```

Tests verify checkpointer isolates conversations.

## Mocking Strategy

### Unit Tests
- Mock external dependencies (ModelAgent, create_agent, LLMs)
- Test logic in isolation
- Fast execution

### Integration Tests
- Use real graph with MemorySaver checkpointer
- Test actual node interactions
- Verify end-to-end behavior

## Dependencies

Tests use:
- `pytest` - test framework
- `pytest-anyio` - async test support
- `unittest.mock` - mocking for unit tests
- `langgraph.checkpoint.memory.MemorySaver` - in-memory checkpointing

## Continuous Integration

Tests should:
- ✅ Pass on all commits
- ✅ Run in CI/CD pipeline
- ✅ Maintain >80% coverage
- ✅ Complete in <5 minutes

## Contributing

When adding features:
1. Add unit tests for new functions
2. Add integration tests for new flows
3. Update this README with new test cases
4. Ensure all tests pass before PR
