import os
from typing import Optional

from atlassian import Jira
from langchain_core.tools import tool


# ---- Jira client setup ----
jira = Jira(
    url=os.environ["JIRA_INSTANCE_URL"],  # e.g. https://your-domain.atlassian.net
    username=os.environ["JIRA_USERNAME"],
    password=os.environ["JIRA_API_TOKEN"],
    cloud=True,
)

DONE_HINTS = ("done", "close", "closed", "resolve", "resolved", "complete", "completed")


# ---- Helpers ----
def _to_text(value) -> str:
    """Convert a Jira description (plain/wiki string or ADF dict) into plain text."""
    if not value:
        return "(no description)"
    if isinstance(value, str):
        return value

    parts = []

    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            node_type = node.get("type")
            if node_type == "text":
                parts.append(node.get("text", ""))
            elif node_type == "hardBreak":
                parts.append("\n")
            walk(node.get("content", []))
            if node_type in {"paragraph", "heading", "listItem", "codeBlock"}:
                parts.append("\n")

    walk(value)
    return "".join(parts).strip() or "(no description)"


def _format_issue(issue: dict) -> str:
    f = issue.get("fields", {})
    assignee = f.get("assignee")
    parent = f.get("parent")

    lines = [
        f"Key: {issue.get('key')}",
        f"Type: {(f.get('issuetype') or {}).get('name')}",
        f"Summary: {f.get('summary')}",
        f"Status: {(f.get('status') or {}).get('name')}",
        f"Priority: {(f.get('priority') or {}).get('name')}",
        f"Assignee: {assignee.get('displayName') if assignee else 'Unassigned'}",
    ]
    if parent:
        lines.append(
            f"Parent: {parent.get('key')} - {parent.get('fields', {}).get('summary')}"
        )

    lines.append(f"Description:\n{_to_text(f.get('description'))}")

    subtasks = f.get("subtasks") or []
    if subtasks:
        lines.append("Subtasks:")
        for s in subtasks:
            sf = s.get("fields", {})
            lines.append(
                f"  - {s.get('key')}: {sf.get('summary')} "
                f"[{(sf.get('status') or {}).get('name')}]"
            )
    else:
        lines.append("Subtasks: none")
    return "\n".join(lines)


def _get_transitions(issue_key: str) -> list:
    data = jira.get(f"rest/api/2/issue/{issue_key}/transitions") or {}
    return data.get("transitions", [])


def _do_transition(issue_key: str, transition_id, comment: str = "", fields: Optional[dict] = None):
    payload = {"transition": {"id": str(transition_id)}}
    if fields:
        payload["fields"] = fields
    if comment:
        payload["update"] = {"comment": [{"add": {"body": comment}}]}
    jira.post(f"rest/api/2/issue/{issue_key}/transitions", data=payload)


def _is_done(issue_key: str) -> bool:
    issue = jira.issue(issue_key, fields="status")
    category = (issue["fields"]["status"].get("statusCategory") or {}).get("key")
    return category == "done"


def _close(issue_key: str, comment: str = "") -> str:
    """Close one issue by taking a transition that lands in a 'done' status.
    Raises on failure so callers can report it."""
    if _is_done(issue_key):
        return f"{issue_key} is already closed."

    transitions = _get_transitions(issue_key)
    done_options = [
        t for t in transitions
        if (t.get("to", {}).get("statusCategory") or {}).get("key") == "done"
    ]
    if not done_options:
        available = ", ".join(f"{t['name']} -> {t['to']['name']}" for t in transitions)
        raise RuntimeError(f"No transition to a done status. Available: {available}")

    # Prefer a transition whose name looks like Done/Close/Resolve, else take the first.
    chosen = next(
        (t for t in done_options if t["name"].lower() in DONE_HINTS
         or t["to"]["name"].lower() in DONE_HINTS),
        done_options[0],
    )

    try:
        _do_transition(issue_key, chosen["id"], comment)
    except Exception as e:
        # Some workflows require a resolution on the transition screen.
        if "resolution" in str(e).lower():
            _do_transition(issue_key, chosen["id"], comment, fields={"resolution": {"name": "Done"}})
        else:
            raise
    return f"{issue_key} closed (status: '{chosen['to']['name']}')."


# ---- Tools: read ----
@tool
def get_jira_issue(issue_key: str) -> str:
    """Read a Jira ticket: type, summary, status, priority, assignee, parent,
    full description, and a list of its subtasks (key, summary, status).

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
    """
    try:
        issue = jira.issue(issue_key)
    except Exception as e:
        return f"Error fetching {issue_key}: {e}"
    return _format_issue(issue)


@tool
def get_jira_subtasks(issue_key: str) -> str:
    """Read the full details (including descriptions) of every subtask of a ticket.

    Args:
        issue_key: Key of the PARENT ticket, e.g. 'PROJ-123'.
    """
    try:
        parent = jira.issue(issue_key, fields="subtasks,summary")
        subtasks = parent["fields"].get("subtasks") or []
        if not subtasks:
            return f"{issue_key} has no subtasks."
        details = [_format_issue(jira.issue(s["key"])) for s in subtasks]
    except Exception as e:
        return f"Error fetching subtasks of {issue_key}: {e}"
    return f"{issue_key} has {len(details)} subtask(s):\n\n" + "\n\n---\n\n".join(details)


@tool
def search_jira_issues(jql: str, max_results: int = 10) -> str:
    """Search Jira issues using a JQL query.

    Args:
        jql: JQL query string, e.g. 'project = PROJ AND status = "To Do"'.
        max_results: Max number of results to return.
    """
    try:
        result = jira.jql(jql, limit=max_results)
    except Exception as e:
        return f"Error searching issues: {e}"

    issues = result.get("issues", [])
    if not issues:
        return "No issues found."

    lines = []
    for issue in issues:
        f = issue["fields"]
        lines.append(f"{issue['key']}: {f.get('summary')} [{(f.get('status') or {}).get('name')}]")
    return "\n".join(lines)


# ---- Tools: create ----
@tool
def create_jira_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
) -> str:
    """Open (create) a new Jira ticket in a project.

    Args:
        project_key: Project key, e.g. 'PROJ'.
        summary: Ticket title.
        issue_type: Issue type, e.g. Task, Bug, Story.
        description: Ticket description.
    """
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type},
    }
    try:
        result = jira.issue_create(fields=fields)
    except Exception as e:
        return f"Error creating issue: {e}"

    key = result.get("key")
    return f"Created issue {key}: {jira.url}/browse/{key}"


@tool
def create_jira_subtask(
    parent_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Sub-task",
) -> str:
    """Create a subtask under an existing ticket.

    Args:
        parent_key: Key of the parent ticket, e.g. 'PROJ-123'.
        summary: Subtask title.
        description: Subtask description.
        issue_type: Subtask type name. Usually 'Sub-task'; some team-managed
            projects use 'Subtask'.
    """
    try:
        parent = jira.issue(parent_key, fields="project")
        project_key = parent["fields"]["project"]["key"]
        fields = {
            "project": {"key": project_key},
            "parent": {"key": parent_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
        result = jira.issue_create(fields=fields)
    except Exception as e:
        return f"Error creating subtask under {parent_key}: {e}"

    key = result.get("key")
    return f"Created subtask {key} under {parent_key}: {jira.url}/browse/{key}"


# ---- Tools: status changes ----
@tool
def list_jira_transitions(issue_key: str) -> str:
    """List the statuses a ticket can currently be moved to.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
    """
    try:
        transitions = _get_transitions(issue_key)
    except Exception as e:
        return f"Error fetching transitions for {issue_key}: {e}"
    if not transitions:
        return f"No transitions available for {issue_key}."
    return "\n".join(f"{t['name']} -> {t['to']['name']}" for t in transitions)


@tool
def transition_jira_issue(issue_key: str, status: str, comment: str = "") -> str:
    """Change a ticket's status (e.g. To Do -> In Progress -> In Review).
    To close a ticket use close_jira_issue instead.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
        status: Target status or transition name, e.g. 'In Progress'.
        comment: Optional comment to add during the transition.
    """
    try:
        transitions = _get_transitions(issue_key)
        wanted = status.strip().lower()
        match = next(
            (t for t in transitions
             if t["name"].lower() == wanted or t["to"]["name"].lower() == wanted),
            None,
        )
        if not match:
            available = ", ".join(f"{t['name']} -> {t['to']['name']}" for t in transitions)
            return f"'{status}' not available for {issue_key}. Available: {available}"
        _do_transition(issue_key, match["id"], comment)
    except Exception as e:
        return f"Error transitioning {issue_key}: {e}"
    return f"{issue_key} moved to '{match['to']['name']}'."


@tool
def close_jira_issue(issue_key: str, comment: str = "", close_subtasks: bool = False) -> str:
    """Close a ticket (move it to a Done/Closed/Resolved status).

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
        comment: Optional closing comment (e.g. what was done).
        close_subtasks: If true, close any open subtasks first.
    """
    results = []
    try:
        if close_subtasks:
            parent = jira.issue(issue_key, fields="subtasks")
            for s in parent["fields"].get("subtasks") or []:
                try:
                    results.append(_close(s["key"]))
                except Exception as e:
                    results.append(f"Could not close subtask {s['key']}: {e}")
        results.append(_close(issue_key, comment))
    except Exception as e:
        results.append(f"Error closing {issue_key}: {e}")
    return "\n".join(results)


# ---- Tools: misc ----
@tool
def add_jira_comment(issue_key: str, comment: str) -> str:
    """Add a comment to a Jira issue.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
        comment: Comment text to add.
    """
    try:
        jira.issue_add_comment(issue_key, comment)
    except Exception as e:
        return f"Error adding comment to {issue_key}: {e}"
    return f"Comment added to {issue_key}."


@tool
def assign_jira_issue(issue_key: str, assignee: str) -> str:
    """Assign a Jira issue to a user.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
        assignee: Account ID (Jira Cloud) of the user to assign the issue to.
    """
    try:
        jira.assign_issue(issue_key, assignee)
    except Exception as e:
        return f"Error assigning {issue_key}: {e}"
    return f"{issue_key} assigned to {assignee}."


# All tools to bind to a model/agent
jira_tools = [
    get_jira_issue,
    get_jira_subtasks,
    search_jira_issues,
    create_jira_issue,
    create_jira_subtask,
    list_jira_transitions,
    transition_jira_issue,
    close_jira_issue,
    add_jira_comment,
    assign_jira_issue,
]