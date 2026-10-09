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
from pathlib import Path
from typing import Callable

from langchain.tools import tool
from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)

# Coding workspace: repositories + coder output only (agent config lives in src/agent/profile/).
# Outside the repo so `langgraph dev` hot reload is not triggered; mount as a volume in prod.
WORKSPACE_DIR = Path(
    os.environ.get("WORKSPACE_DIR") or os.environ.get("CODER_WORKSPACE_DIR") or "~/agent-workspace"
).expanduser().resolve()
# Catalog name that grants an agent access to /workspace/ through the built-in file tools
WORKSPACE_TOOL = "workspace"


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


def find_jira_user(jira, query: str) -> dict:
    """Find one Jira user by display name or email; raise if none or ambiguous."""
    users = [u for u in jira.user_find_by_user_string(query=query) if u.get("accountType") == "atlassian"]
    exact = [
        u for u in users
        if query.lower() in {str(u.get("displayName", "")).lower(), str(u.get("emailAddress", "")).lower()}
    ]
    matches = exact or users
    if len(matches) != 1:
        names = [u.get("displayName") for u in users] or "none"
        raise ValueError(f"Expected exactly one Jira user for {query!r}, found: {names}")
    return matches[0]


@tool
def submit_jira_ticket_for_review(issue_key: str, comment: str, reviewer: str = "", status: str = "In Review") -> str:
    """Hand a finished ticket to a reviewer: move it to review, add a comment mentioning the reviewer, assign it to them.

    Args:
        issue_key: Jira issue key, e.g. "PP-3"
        comment: What was done: summary of the change, files under /workspace/, how to test
        reviewer: Jira display name or email of the reviewer; defaults to JIRA_REVIEWER env var
        status: Target review status, e.g. "In Review"
    """
    reviewer = reviewer or os.environ.get("JIRA_REVIEWER", "")
    if not reviewer:
        return "Error: no reviewer given and JIRA_REVIEWER is not set."
    done = []
    try:
        from langchain_community.utilities.jira import JiraAPIWrapper

        jira = JiraAPIWrapper().jira
        user = find_jira_user(jira, reviewer)

        transitions = jira.get_issue_transitions(issue_key)
        target = next((t["to"] for t in transitions if t["to"].lower() == status.lower()), None) or next(
            (t["to"] for t in transitions if "review" in t["to"].lower()), None
        )
        if target is None:
            return f"Error: no review transition for {issue_key}. Available: {[t['to'] for t in transitions]}"
        jira.set_issue_status(issue_key, target)
        done.append(f"moved to {target}")

        # REST v2 wiki markup mention; renders as @displayName in Jira Cloud
        jira.issue_add_comment(issue_key, f"[~accountid:{user['accountId']}] {comment}")
        done.append(f"commented mentioning {user['displayName']}")

        jira.assign_issue(issue_key, account_id=user["accountId"])
        done.append(f"assigned to {user['displayName']}")
        return f"{issue_key}: " + ", ".join(done) + "."
    except Exception as e:
        partial = f" Completed before the error: {', '.join(done)}." if done else ""
        return f"Error submitting {issue_key} for review: {type(e).__name__}: {e}.{partial}"


# ---------- Slack ----------
def get_slack_tools():
    """Slack tools - Slack.py validates SLACK_BOT_TOKEN / SLACK_CHANNEL_ID at import."""
    from agent.core.slack import get_slack_tools as _get

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
    "jira_submit_review": ToolEntry(
        "Hand a finished Jira ticket to a reviewer: move to In Review, comment mentioning the reviewer, assign to them.",
        lambda: [submit_jira_ticket_for_review],
    ),
    WORKSPACE_TOOL: ToolEntry(
        "Coding workspace at /workspace/ (repositories + code output): ls, read_file, write_file, edit_file, glob, grep. Only for agents that write code.",
        # No extra tool: deepagents' built-in file tools do the work; registry.permissions_for grants the path
        lambda: [],
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
