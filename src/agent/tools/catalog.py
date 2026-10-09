"""Whitelisted tools that the default-agent may assign to created agents.

Agents reference tools by catalog name only, so the default-agent can never
invent or execute arbitrary code. Factories are lazy so missing credentials
(Tavily, Jira, Slack) only fail when an agent that uses them is built.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

from langchain.tools import tool
from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)

# Coder output lives outside the repo so `langgraph dev` hot reload is not triggered
SCRIPT_DIR = os.path.expanduser(os.environ.get("CODER_WORKSPACE_DIR", "~/agent-workspace"))


# ---------- Web search ----------
_search_tool = None
def get_search_tool():
    """Tavily search tool - requires TAVILY_API_KEY env var."""
    global _search_tool
    if _search_tool is None:
        from langchain_community.tools.tavily_search import TavilySearchResults

        _search_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
        )
    return _search_tool


# ---------- Jira ----------
_jira_tools = None
def get_jira_tools():
    """Jira tools wrapped so dict args from tool-calling models are JSON-encoded.

    JiraAPIWrapper calls json.loads() on the raw instructions, which fails
    when the model sends a JSON object instead of a JSON string.
    """
    global _jira_tools
    if _jira_tools is None:
        from langchain_community.agent_toolkits.jira.toolkit import JiraToolkit
        from langchain_community.utilities.jira import JiraAPIWrapper

        jira_api = JiraAPIWrapper()
        toolkit = JiraToolkit.from_jira_api_wrapper(jira_api)

        def wrap(jira_tool):
            def _run(instructions: str | dict) -> str:
                if not isinstance(instructions, str):
                    instructions = json.dumps(instructions)
                try:
                    return jira_tool.api_wrapper.run(jira_tool.mode, instructions)
                except AttributeError as e:
                    # "other" mode does getattr(jira, function); model guessed a bad name
                    return f"Error: {e}. Use a valid atlassian-python-api Jira method name."
                except Exception as e:
                    # Let the model see the error and retry instead of crashing the graph
                    return f"Error: {type(e).__name__}: {e}"

            description = jira_tool.description
            if jira_tool.mode == "other":
                description += (
                    "\nTo change issue status use "
                    '{"function": "set_issue_status", "args": ["PROJ-1", "In Progress"]}. '
                    'List available transitions with {"function": "get_issue_transitions", "args": ["PROJ-1"]}.'
                )

            return StructuredTool.from_function(
                func=_run,
                name=jira_tool.name,
                description=description,
            )

        _jira_tools = [wrap(t) for t in toolkit.get_tools()]
    return _jira_tools


@tool
def get_jira_ticket(issue_key: str) -> str:
    """Read a Jira ticket's summary, description, status and assignee.

    Args:
        issue_key: Jira issue key, e.g. "PP-3"
    """
    try:
        from langchain_community.utilities.jira import JiraAPIWrapper

        jira = JiraAPIWrapper().jira
        fields = jira.issue(issue_key, fields="summary,description,status,assignee")["fields"]
        assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        return (
            f"Ticket: {issue_key}\n"
            f"Summary: {fields.get('summary')}\n"
            f"Status: {fields['status']['name']}\n"
            f"Assignee: {assignee}\n"
            f"Description:\n{fields.get('description') or '(empty)'}"
        )
    except Exception as e:
        return f"Error reading {issue_key}: {type(e).__name__}: {e}"


@tool
def start_jira_ticket(issue_key: str) -> str:
    """Assign a Jira ticket to the current user (the API account) and move it to In Progress.

    Args:
        issue_key: Jira issue key, e.g. "PP-3"
    """
    try:
        from langchain_community.utilities.jira import JiraAPIWrapper

        jira = JiraAPIWrapper().jira
        me = jira.myself()
        jira.assign_issue(issue_key, account_id=me["accountId"])
        jira.set_issue_status(issue_key, "In Progress")
        return f"{issue_key} assigned to {me['displayName']} and moved to In Progress."
    except Exception as e:
        return f"Error starting {issue_key}: {type(e).__name__}: {e}"


# ---------- Coder workspace ----------
def resolve_script_path(file_path: str) -> str | None:
    """Resolve file_path inside SCRIPT_DIR, or None if it points outside it.

    Accepts absolute paths, ~-prefixed paths, or paths relative to SCRIPT_DIR.
    """
    path = os.path.expanduser(file_path.replace("\\", "/"))
    if not os.path.isabs(path):
        path = os.path.join(SCRIPT_DIR, path.lstrip("/"))
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(SCRIPT_DIR)
    if os.path.commonpath([real_path, real_root]) != real_root:
        return None
    return real_path


@tool
def save_script_file(file_path: str, content: str) -> str:
    """Write content to a file inside the coder workspace (~/agent-workspace).

    Args:
        file_path: Path of the file, relative to the coder workspace
        content: The content to write to the file

    Returns:
        Success message with file path, or an error if the path is outside the coder workspace
    """
    resolved = resolve_script_path(file_path)
    if resolved is None:
        return f"Error: {file_path} is outside {SCRIPT_DIR}. The coder may only write files inside {SCRIPT_DIR}."
    file_path = resolved
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing to {file_path}: {str(e)}"


# ---------- Slack ----------
def get_slack_tools():
    """Slack tools - Slack.py validates SLACK_BOT_TOKEN / SLACK_CHANNEL_ID at import."""
    from agent.tools.slack.Slack import get_slack_tools as _get

    return _get()


# ---------- Catalog ----------
@dataclass(frozen=True)
class ToolEntry:
    """A catalog entry: description shown to the default-agent + lazy factory."""

    description: str
    factory: Callable[[], list[BaseTool]]


TOOL_CATALOG: dict[str, ToolEntry] = {
    "web_search": ToolEntry(
        "Search the internet via Tavily (needs TAVILY_API_KEY).",
        lambda: [get_search_tool()],
    ),
    "jira": ToolEntry(
        "Full Jira toolkit: JQL search, create issue, project list, any Jira API call.",
        get_jira_tools,
    ),
    "jira_read_ticket": ToolEntry(
        "Read one Jira ticket's summary, description, status and assignee.",
        lambda: [get_jira_ticket],
    ),
    "jira_start_ticket": ToolEntry(
        "Assign a Jira ticket to the bot account and move it to In Progress.",
        lambda: [start_jira_ticket],
    ),
    "save_script_file": ToolEntry(
        f"Write files inside the coder workspace ({SCRIPT_DIR}).",
        lambda: [save_script_file],
    ),
    "slack": ToolEntry(
        "Send, read and reply to messages in the team Slack channel (needs SLACK_BOT_TOKEN, SLACK_CHANNEL_ID).",
        get_slack_tools,
    ),
}


def resolve_tools(names: list[str]) -> list[BaseTool]:
    """Build tools for catalog names; unknown or failing entries are skipped and logged."""
    tools: list[BaseTool] = []
    for name in names:
        entry = TOOL_CATALOG.get(name)
        if entry is None:
            logger.warning("Unknown tool %r skipped", name)
            continue
        try:
            tools.extend(entry.factory())
        except Exception as e:
            logger.warning("Tool %r unavailable: %s: %s", name, type(e).__name__, e)
    return tools
