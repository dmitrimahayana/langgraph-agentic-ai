# LangGraph Agent Harness

A chat system where **one AI agent manages a team of other AI agents**.

You talk to a single **default agent**. It can:

- answer you directly,
- **hand work to specialist agents** (a coder, a researcher, a Jira admin, …),
- **create new agents through chat** — "create an agent called `pm` that manages Jira" — and give them **tools** and **skills**.

Every agent is just a **folder of markdown files**. No Python needed to add or change an agent.

Built with [LangGraph](https://langchain-ai.github.io/langgraph/) (runs and saves conversations) and [deepagents](https://github.com/langchain-ai/deepagents) (builds the agents).

---

## Table of contents

1. [Words you need to know](#1-words-you-need-to-know)
2. [Quick start](#2-quick-start)
3. [Project layout](#3-project-layout)
4. [How one message flows through the system](#4-how-one-message-flows-through-the-system)
5. [Agent folders (profiles)](#5-agent-folders-profiles)
6. [Tools](#6-tools)
7. [Skills](#7-skills)
8. [The coding workspace](#8-the-coding-workspace)
9. [Safety rules](#9-safety-rules)
10. [The code, file by file](#10-the-code-file-by-file)
11. [Talking to the default agent](#11-talking-to-the-default-agent)
12. [How-to recipes](#12-how-to-recipes)
13. [Where data is stored](#13-where-data-is-stored)
14. [Testing](#14-testing)
15. [Troubleshooting](#15-troubleshooting)
16. [Running in production](#16-running-in-production)
17. [Web frontend](#17-web-frontend)

---

## 1. Words you need to know

| Word | Meaning |
|---|---|
| **LLM** | The AI model that reads text and writes text (here: `gemma4:31b-cloud` via Ollama). |
| **Agent** | An LLM + a system prompt + a set of tools, running in a loop until it has a final answer. |
| **System prompt** | Instructions given to the LLM before the conversation: who it is and how to behave. Stored in `SOUL.md`. |
| **Tool** | A Python function the LLM is allowed to call, e.g. "read a Jira ticket". The LLM decides *when* to call it and *with which arguments*; our code runs it and gives the result back. |
| **Skill** | A markdown guide ("how to do X step by step") an agent can open when it needs it. Stored in `SKILL.md`. |
| **Default agent** | The agent you chat with. The entry point. |
| **Subagent** | Any other agent. The default agent delegates to it with the `task` tool. |
| **Profile** | One agent's folder: `src/agent/profile/<name>/`. |
| **Catalog** | The fixed list of tools agents are allowed to have (`core/catalog.py`). |
| **Workspace** | The folder where the coder writes code: `~/agent-workspace`. |
| **Thread** | One conversation. LangGraph saves every thread's messages. |
| **LangGraph** | Framework that runs our code as a "graph" of steps and saves conversation history. |
| **deepagents** | Library that builds an agent (the LLM loop) with delegation, file tools and skills built in. |

### What an agent loop looks like

Every agent — default or subagent — runs this loop, written here in plain Python:

```python
messages = [system_prompt, user_message]
while True:
    reply = llm(messages, tools=agent_tools)        # LLM answers OR asks to call tools
    if not reply.tool_calls:
        return reply.text                           # done: final answer
    for call in reply.tool_calls:
        result = run_tool(call.name, call.args)     # we run the Python function
        messages.append(result)                     # LLM sees the result next round
```

That's all an "agent" is. The rest of this project decides **which prompt, which tools and which skills** each agent gets.

---

## 2. Quick start

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (or pip)
- [Ollama](https://ollama.com) running locally (`ollama serve`), signed in for cloud models
- Optional: Jira Cloud account + API token, Tavily API key, Slack bot token

### Install

```bash
git clone <this repo>
cd langgraph-agentic-ai
uv sync            # or: pip install -e . "langgraph-cli[inmem]"
```

### Configure `.env`

Create a `.env` file in the project root:

```bash
# --- Jira (coder + admin agents) ---
JIRA_INSTANCE_URL=https://your-company.atlassian.net
JIRA_USERNAME=you@example.com
JIRA_API_TOKEN=...
JIRA_CLOUD=True
JIRA_REVIEWER=dmitri            # optional: default reviewer for submit-for-review

# --- Web search (researcher agent) ---
TAVILY_API_KEY=...

# --- Slack (slack agent) ---
SLACK_BOT_TOKEN=...
SLACK_CHANNEL_ID=...

# --- Coding workspace ---
WORKSPACE_DIR=~/agent-workspace  # optional, this is the default

# --- Model ---
OLLAMA_BASE_URL=http://localhost:11434   # optional, auto-detected
OLLAMA_TIMEOUT=180                       # optional, seconds per model call

# --- Tracing (optional) ---
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=...

# --- Production database (optional) ---
POSTGRES_URI=postgresql://...
```

Missing keys are fine: an agent whose tool needs a missing key simply starts **without that tool**, and a warning is logged.

### Run

```bash
uv run langgraph dev
```

This starts the server at `http://localhost:2024` and opens **LangGraph Studio** in your browser, where you can chat and see every step.

### Try it

```
> list agents
> take PP-3 and implement it
> create an agent "pm" with the jira tool that writes weekly status reports
> ask pm to summarise the tickets in project PP
```

---

## 3. Project layout

```
langgraph-agentic-ai/
├── langgraph.json              ← tells LangGraph where the graph is (src/agent/graph.py:graph)
├── pyproject.toml              ← Python dependencies
├── .env                        ← secrets & settings (not in git)
├── src/agent/
│   ├── graph.py                ← ENTRY POINT: runs on every message
│   ├── registry.py             ← reads/writes agent folders, builds agents
│   ├── model.py                ← creates the Ollama LLM client
│   ├── core/                   ← shared Python code
│   │   ├── catalog.py          ← tools agents can be given (Jira, web search, workspace, Slack)
│   │   ├── manage.py           ← tools only the default agent has (create_agent, save_skill, …)
│   │   └── slack.py            ← Slack tool classes
│   └── profile/                ← DATA: one folder per agent (no Python here)
│       ├── default/            ← the agent you chat with
│       ├── coder/              ← writes code, works Jira tickets
│       ├── researcher/         ← web research
│       ├── admin/              ← Jira administration
│       └── slack/              ← Slack messages
├── tests/                      ← unit & integration tests
└── static/                     ← simple web chat UI

~/agent-workspace/              ← code the coder writes (outside the repo)
```

**Golden rule:** `.py` files are the **engine**. `profile/` is the **configuration**. To change what agents do, you edit markdown in `profile/` — not Python.

---

## 4. How one message flows through the system

You type **"take PP-4 and implement it"**. Here is everything that happens, in order.

```
 You
  │  "take PP-4 and implement it"
  ▼
 LangGraph server  (saves the message in the thread)
  │
  ▼
 graph.py → default_agent()                       ← the only step in the graph
  │
  ├─ 1. BUILD (fresh, every message)
  │     registry.list_agents()        reads every folder in src/agent/profile/
  │     registry.build_subagents()    coder, researcher, admin, slack → subagent configs
  │     create_deep_agent(...)        default agent = default/SOUL.md
  │                                   + management tools + all subagents
  │
  ├─ 2. RUN the default agent's loop
  │     LLM thinks: "coding ticket → coder"
  │     LLM calls:  task(subagent_type="coder",
  │                      description="Take Jira ticket PP-4 and implement it...")
  │        │
  │        ▼
  │     CODER's own loop  (coder/SOUL.md, coder/tools/TOOLS.md, coder/skills/)
  │        reads skill  jira-workflow
  │        calls        get_jira_ticket("PP-4")                → requirements
  │        calls        start_jira_ticket("PP-4")              → In Progress, assigned to bot
  │        calls        write_file("/workspace/pp-4/main.rs")  → ~/agent-workspace/pp-4/main.rs
  │        calls        submit_jira_ticket_for_review("PP-4", reviewer="dmitri", comment=...)
  │                                                            → In Review, @dmitri comment, assigned
  │        returns      "Done: implemented ..., files ..., PP-4 is In Review"
  │        │
  │        ▼
  │     default LLM reads the coder's report, writes the reply to you
  │
  └─ 3. RETURN only the new messages → LangGraph saves them in the thread
  ▼
 You see the answer
```

### Why is the agent rebuilt on every message?

A LangGraph graph is **fixed** once the server starts — you cannot add new steps while it runs. So instead of making each agent a graph step, agents are **data** (folders) and the single step reads the folders every time.

Results:

- An agent created in chat is usable **from your next message**.
- If you edit a `SOUL.md` by hand, the change applies **on the next message** — no restart.

### What the subagent sees

A subagent does **not** see your conversation. It only sees the `description` the default agent wrote in the `task` call. That's why the default agent's prompt tells it to write complete, self-contained task descriptions.

---

## 5. Agent folders (profiles)

Every agent is a folder in `src/agent/profile/`:

```
src/agent/profile/coder/
├── souls/
│   └── SOUL.md                  ← who the agent is
├── tools/
│   └── TOOLS.md                 ← which tools it gets
└── skills/
    └── jira-workflow/
        └── SKILL.md             ← a step-by-step guide it can read
```

A folder counts as an agent only if it has `souls/SOUL.md`. The folder name is the agent's name (lowercase letters, digits, hyphens: `release-manager`).

### `souls/SOUL.md` — identity and system prompt

```markdown
---
name: coder
description: Picks up Jira tickets, implements the code in the coding workspace, and hands the ticket to the reviewer.
model: ollama:gemma4:31b-cloud
---

# Profile: Coder Specialist

## Objective
Executes coding tasks as soon as they are received...
```

| Part | Used for |
|---|---|
| `name` | Must match the folder name. |
| `description` | **Very important.** The default agent reads it to decide *when to delegate* to this agent. Keep it one clear sentence. |
| `model` | Which LLM this agent uses. `ollama:<model>` uses Ollama; other values (e.g. `openai:gpt-4o`) are passed to LangChain's `init_chat_model`. |
| Everything below `---` | The system prompt. |

### `tools/TOOLS.md` — tool list

```markdown
# Tools

One catalog tool name per line (see src/agent/core/catalog.py).

- workspace
- jira_read_ticket
- jira_start_ticket
- jira_submit_review
```

Only lines starting with `- ` count. Each name must exist in the [tool catalog](#6-tools); unknown names are ignored with a warning.

### `skills/<skill-name>/SKILL.md` — guides

See [Skills](#7-skills).

### The special `default` folder

`profile/default/` is the agent **you** talk to. It is built differently from the others:

- It always gets the **management tools** (create/update/delete agents and skills) on top of its `TOOLS.md`.
- It gets every other folder as a **subagent** it can delegate to.
- It cannot be deleted.

### The agents that ship with the project

| Agent | Tools | Skills | Does |
|---|---|---|---|
| `default` | management tools | – | Talks to you, manages the team, delegates |
| `coder` | `workspace`, `jira_read_ticket`, `jira_start_ticket`, `jira_submit_review` | `jira-workflow` | Implements Jira tickets in the workspace and hands them to review |
| `researcher` | `web_search` | `web-research` | Internet research with sources |
| `admin` | `jira` (full toolkit) | `jira-workflow` | Any Jira administration |
| `slack` | `slack` | – | Sends/reads Slack messages |

---

## 6. Tools

### The tool catalog

Agents can only get tools listed in `TOOL_CATALOG` in [`src/agent/core/catalog.py`](src/agent/core/catalog.py). This is a **whitelist**: the LLM can combine existing tools, but can never invent new code to run.

| Name in `TOOLS.md` | Python tool(s) | What it does | Needs |
|---|---|---|---|
| `web_search` | `tavily_search_results_json` | Search the internet | `TAVILY_API_KEY` |
| `jira` | `jql_query`, `create_issue`, `catch_all_jira_api`, … | Full Jira toolkit (powerful!) | Jira env vars |
| `jira_read_ticket` | `get_jira_ticket` | Read one ticket's summary, description, status, assignee | Jira env vars |
| `jira_start_ticket` | `start_jira_ticket` | Assign ticket to the bot + move to **In Progress** | Jira env vars |
| `jira_submit_review` | `submit_jira_ticket_for_review` | Move to **In Review** + comment mentioning the reviewer + assign to reviewer | Jira env vars |
| `workspace` | *(none — a permission)* | Allows the built-in file tools on `/workspace/` | – |
| `slack` | `slack_send_message`, `slack_read_history`, `slack_reply_thread` | Team Slack channel | Slack env vars |

### Built-in tools every agent has

deepagents adds these to every agent automatically:

| Tool | Purpose |
|---|---|
| `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep` | File tools — *where* they can read/write is controlled by [safety rules](#9-safety-rules) |
| `execute` | Shell commands — listed by deepagents, but **our file backends don't support a shell**, so calls return an error |
| `task` | Delegate to a subagent (only useful for the default agent) |

### Management tools (default agent only)

Defined in [`src/agent/core/manage.py`](src/agent/core/manage.py):

| Tool | Does |
|---|---|
| `list_tools` | Show the catalog |
| `list_agents` / `get_agent` | Show agents / one agent's full config |
| `create_agent` | Create `profile/<name>/` with `SOUL.md`, `TOOLS.md`, `skills/` |
| `update_agent` | Change description, prompt, model or tool list |
| `delete_agent` | Delete a folder (asks you to confirm first) |
| `list_skills` / `read_skill` | Show skills |
| `save_skill` | Create or overwrite a skill in an agent's folder |
| `copy_skill` | Copy a skill from one agent to another |
| `delete_skill` | Remove a skill (asks you to confirm first) |

These tools **return error messages instead of crashing**. If the LLM sends a bad tool name, it gets back `Error: Unknown tools ['x']. Available: [...]` and fixes its own call.

### How a tool name becomes a real tool

```python
TOOL_CATALOG = {
    "jira_read_ticket": ToolEntry(
        description="Read one Jira ticket's summary, description, status and assignee.",
        factory=lambda: [get_jira_ticket],     # creates the tool only when needed
    ),
    ...
}

resolve_tools(["jira_read_ticket", "web_search"])   # → [get_jira_ticket, TavilySearchResults(...)]
```

The `factory` runs only when an agent that uses the tool is built, so a missing API key only affects that one agent.

---

## 7. Skills

A **skill** is a markdown guide for a specific job. Format ([Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) standard):

```markdown
---
name: jira-workflow
description: REQUIRED for any task that mentions a Jira ticket key (e.g. PP-3). Read ticket, start it, implement, then hand it to the reviewer.
---

# Jira Workflow

## Steps
1. Read — call `get_jira_ticket` ...
2. Start — call `start_jira_ticket` ...
...
```

### How agents use skills ("progressive disclosure")

1. The agent's system prompt only lists each skill's **name + description** (cheap).
2. When the agent decides a skill is relevant, it **reads the full `SKILL.md`** with `read_file`.
3. It then follows the steps.

So the **description decides whether the skill gets used**. Write it like a trigger: *"REQUIRED for any task that…"*, *"Use when…"*.

### SOUL.md vs SKILL.md — what goes where?

| Put it in `SOUL.md` | Put it in a `SKILL.md` |
|---|---|
| Who the agent is, its scope, its style, output format | A specific procedure: "how to work a Jira ticket", "how to write release notes" |
| Always relevant | Only relevant for some tasks |

### Skills belong to one agent

Each agent has its **own copy** of its skills. `coder/skills/jira-workflow` and `admin/skills/jira-workflow` are **different files** — editing one does not change the other. Use `copy_skill` to share.

---

## 8. The coding workspace

The coder writes code into a separate folder, **outside the repo**:

| | |
|---|---|
| Real folder | `WORKSPACE_DIR` env var, default `~/agent-workspace` |
| Path the agent sees | `/workspace/` |
| Example | the agent writes `/workspace/pp-4/main.rs` → file appears at `~/agent-workspace/pp-4/main.rs` |
| Contents | Only repositories and code output — **never** agent config |
| Who can use it | Only agents with `- workspace` in their `TOOLS.md` (the coder) |

Why outside the repo? `langgraph dev` restarts the server when `.py` files in the project change. If the coder wrote Python into the repo, the server would restart in the middle of its work.

> The coder can read, write and edit files, but cannot run shell commands (no `git`, no running tests) yet.

---

## 9. Safety rules

Agents never touch the disk directly. All file tools go through a **backend** that maps the paths agents see to real storage ([`registry.make_backend`](src/agent/registry.py)):

```
Path the agent uses               Real storage
──────────────────────────────    ─────────────────────────────────────────────
/workspace/...                 →  ~/agent-workspace/...              (disk)
/agents/<name>/skills/...      →  src/agent/profile/<name>/skills/   (disk)
anything else (/notes.md, …)   →  memory only, thrown away after the message
```

`SOUL.md`, `TOOLS.md` and the Python code are **not mapped at all** — no agent can rewrite its own prompt, its tool list, or the code.

On top of that, every agent gets **permission rules** ([`registry.permissions_for`](src/agent/registry.py)):

| Rule | Effect |
|---|---|
| Write only your **own** `skills/` folder | The coder can't overwrite the admin's skills |
| `/workspace/` only with `- workspace` in `TOOLS.md` | The researcher gets "permission denied" there |

Other protections:

- **Tool whitelist** — only catalog tools ([section 6](#6-tools)).
- **Name validation** — names must be `lowercase-with-hyphens`, which blocks tricks like `../../etc`.
- **Management tools only for the default agent** — subagents can't create or delete agents.
- **Deleting asks first** — the default agent's prompt requires your explicit "yes" before `delete_agent` / `delete_skill`.

---

## 10. The code, file by file

### `src/agent/graph.py` — the entry point

```python
class HarnessState(MessagesState):        # the saved state = list of chat messages
    ...

def build_default_agent(model_override=None):
    specs = registry.list_agents()                         # read all profile folders
    default = <the spec named "default">
    others  = <all other specs>
    return create_deep_agent(
        model=registry.load_model(default.model),
        tools=MANAGEMENT_TOOLS + resolve_tools(default.tools),
        system_prompt=default.system_prompt,
        skills=["/agents/default/skills/"],
        subagents=registry.build_subagents(others),        # ← every other agent
        backend=registry.make_backend(specs),              # ← file path mapping
        permissions=registry.permissions_for(default),     # ← file rules
        middleware=registry.model_middleware(),            # ← retry on model errors
    )

async def default_agent(state, runtime):                   # the graph's only step
    agent = await asyncio.to_thread(build_default_agent)   # file reading in a thread
    result = await agent.ainvoke({"messages": state["messages"]})
    return {"messages": <only the new messages>}

# graph:  START → default_agent → END
```

Two details worth knowing:

- **`asyncio.to_thread`** — `langgraph dev` forbids slow blocking work (like reading files) directly inside `async` functions, so building runs in a worker thread.
- **Only new messages are returned** — LangGraph *appends* returned messages to the history, so returning the whole list would duplicate it.

### `src/agent/registry.py` — folders ⇄ agents

Mostly plain Python (`pathlib`, `yaml`, `re`, `shutil`). It translates between three forms of an agent:

```
 profile/coder/  ──load_agent──▶  AgentSpec  ──build_subagents──▶  SubAgent dict
 (markdown files) ◀──save_agent──  (Python)                         (for deepagents)
```

| Function / class | Job |
|---|---|
| `PROFILE_DIR` | `src/agent/profile/` |
| `AgentSpec` | Pydantic model: `name, description, system_prompt, model, tools, skills`. Validates names and tool names. |
| `load_agent(path)` | Folder → `AgentSpec` |
| `list_agents()` / `get_agent(name)` | All agents / one agent |
| `save_agent(spec)` | `AgentSpec` → writes `SOUL.md` + `TOOLS.md`, creates `skills/` |
| `delete_agent(name)` | Removes the folder (never `default`) |
| `save_skill` / `copy_skill` / `delete_skill` / `list_skills` / `read_skill` | Skill files |
| `split_frontmatter` / `with_frontmatter` | Read/write the `---` YAML header |
| `parse_tools_md` | Pull `- name` lines out of `TOOLS.md` |
| `load_model(name)` | `"ollama:…"` → `ChatOllama`; anything else passed through |
| `model_middleware()` | Retries failed model calls (2×) |
| `make_backend(specs)` | Path mapping ([section 9](#9-safety-rules)) |
| `permissions_for(spec)` | File rules per agent ([section 9](#9-safety-rules)) |
| `build_subagents(specs)` | `AgentSpec` → deepagents `SubAgent` dicts |

### `src/agent/core/catalog.py` — tools agents can have

The real tool functions (Jira, web search, Slack) plus `TOOL_CATALOG` and `resolve_tools`. Add new tools here ([recipe](#add-a-new-kind-of-tool-python)).

### `src/agent/core/manage.py` — the default agent's admin tools

Thin `@tool` wrappers around registry functions. They are plain `def` (not `async def`) on purpose: LangChain runs plain tools in a worker thread, so their file writes never block the server.

### `src/agent/model.py` — the LLM client

Creates `ChatOllama`, auto-detects the Ollama URL (local vs Docker), and sets a request timeout (`OLLAMA_TIMEOUT`, default 180 s) so a stuck request can't hang forever.

---

## 11. Talking to the default agent

Things you can say:

| You say | What happens |
|---|---|
| `list agents` | Shows every agent with its tools and skills |
| `show agent coder` | Shows coder's full config including its prompt |
| `list tools` | Shows the tool catalog |
| `list skills` | Shows every agent's skills |
| `create an agent "pm" with the jira tool that writes weekly reports` | Creates `profile/pm/` |
| `give pm the web_search tool too` | Updates `pm/tools/TOOLS.md` |
| `give pm a skill "weekly-report": ...steps...` | Creates `pm/skills/weekly-report/SKILL.md` |
| `copy the jira-workflow skill from coder to pm` | Copies the skill folder |
| `ask pm to write this week's report` | Delegates with `task(subagent_type="pm")` |
| `take PP-4 and implement it` | Delegates to the coder, who follows `jira-workflow` |
| `delete agent pm` | Asks you to confirm, then deletes the folder |

> New or changed agents/skills take effect from your **next** message.

---

## 12. How-to recipes

### Add an agent by hand

```bash
mkdir -p src/agent/profile/pm/{souls,tools,skills}
```

`src/agent/profile/pm/souls/SOUL.md`:

```markdown
---
name: pm
description: Writes weekly project status reports from Jira tickets.
model: ollama:gemma4:31b-cloud
---

You are a project manager. Read the tickets, group them by status, and write a short report.
```

`src/agent/profile/pm/tools/TOOLS.md`:

```markdown
# Tools

- jira
```

Send any message — `pm` now exists.

### Give an agent a tool

Add a `- tool_name` line to its `tools/TOOLS.md`, or say *"give pm the web_search tool"*.

### Add a skill

Create `src/agent/profile/<agent>/skills/<skill-name>/SKILL.md` with `name` + `description` frontmatter, or say *"give pm a skill …"*.

### Change an agent's behaviour

Edit its `souls/SOUL.md` (general behaviour) or a `SKILL.md` (a specific procedure). Applies on the next message.

### Change the reviewer for Jira tickets

Edit step 4 in `src/agent/profile/coder/skills/jira-workflow/SKILL.md` (`reviewer`: `dmitri`), or set `JIRA_REVIEWER` in `.env`.

### Add a new kind of tool (Python)

1. Write the tool in `src/agent/core/catalog.py`:

   ```python
   @tool
   def get_weather(city: str) -> str:
       """Return the current weather for a city.

       Args:
           city: City name, e.g. "Jakarta"
       """
       try:
           ...
           return "28°C, cloudy"
       except Exception as e:
           return f"Error: {e}"          # return errors, don't raise
   ```

   The **docstring is what the LLM reads** to decide when and how to call the tool — write it clearly.

2. Register it in `TOOL_CATALOG`:

   ```python
   "weather": ToolEntry("Current weather for a city.", lambda: [get_weather]),
   ```

3. Add `- weather` to an agent's `TOOLS.md`.

### Use a different model for one agent

Change `model:` in that agent's `SOUL.md`, e.g. `model: ollama:qwen3:32b`.

---

## 13. Where data is stored

| Data | Location | Lifetime |
|---|---|---|
| Conversations (threads) | LangGraph checkpointer — in memory (+ `.langgraph_api/`) with `langgraph dev`, Postgres in production | Per thread |
| Agents, prompts, tools, skills | `src/agent/profile/` | Permanent; commit to git |
| Code written by the coder | `~/agent-workspace/` (`WORKSPACE_DIR`) | Permanent |
| An agent's scratch files during a task | Memory | Thrown away after each message |

Agents created in chat appear in `git status` — review and commit them like code.

---

## 14. Testing

```bash
uv run pytest tests/unit_tests        # fast, no LLM, no network
uv run pytest tests/integration_tests # calls the real model
uv run ruff check src tests           # lint
```

Unit tests ([`tests/unit_tests/test_registry.py`](tests/unit_tests/test_registry.py)) cover creating/updating/deleting agents and skills, `TOOLS.md` parsing, file permissions, the workspace mapping, the submit-for-review tool (with a fake Jira) and that the graph sees every profile folder.

Tests **never write into `src/`**: [`tests/conftest.py`](tests/conftest.py) copies `profile/` into a temporary folder for each test and points `PROFILE_DIR` and `WORKSPACE_DIR` there.

---

## 15. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Tool 'slack' unavailable: SLACK_CHANNEL_ID environment variable not set` in logs | That agent's tool needs env vars. Add them to `.env` or ignore — other agents are unaffected. |
| A new agent isn't used | It only exists from the **next** message. Check it with `list agents`. |
| The agent ignores a skill | Make the skill's `description` a clear trigger ("REQUIRED for any task that…"). Add a one-line reminder in `SOUL.md`. |
| Researcher says "permission denied" on `/workspace/` | Expected — only agents with `- workspace` in `TOOLS.md` may use it. |
| A run shows no response for minutes | Open the run in LangGraph Studio to see which tool is being called. Check `~/.ollama/logs/server.log`: a steady stream of `/api/chat` requests means the agent is **looping**; no requests means a model call is stuck (timeout is `OLLAMA_TIMEOUT`). Cancel the run from Studio. |
| `BlockingError` in `langgraph dev` | Some code did file/network I/O directly inside an `async` function. Move it to a plain function and call it with `asyncio.to_thread`. |
| Wrong Jira user assigned | The review tool looks users up by display name or email and refuses if several match. Use a more exact name or the email. |

### Known limitations

- **No loop limit yet.** An agent that keeps calling tools in a circle runs until cancelled. (Planned: `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`.)
- **No shell in the workspace.** The coder can't run `git` or tests.
- **Progress isn't streamed** from subagents — you see the result when the whole turn finishes; use LangGraph Studio to watch steps.

---

## 16. Running in production

- `langgraph up` or LangGraph Platform saves threads in **Postgres** (`POSTGRES_URI`).
- `src/agent/profile/` ships with the code. Create and tune agents in dev, **commit them**, deploy. Agents created through chat *in production* are lost on the next deploy unless `src/agent/profile/` is a persistent volume.
- Mount `WORKSPACE_DIR` as a **persistent volume** so the coder's output survives restarts.

---

## 17. Web frontend

A simple chat UI is in `static/`.

```bash
uv run langgraph dev        # terminal 1
./start-frontend.sh         # terminal 2
```

Open http://localhost:8080. See [static/README.md](static/README.md).

You can also chat in **LangGraph Studio**, which `langgraph dev` opens automatically — it shows every tool call, subagent run and message, which makes it the best place to learn how the system behaves.
