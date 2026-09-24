import os
from atlassian import Jira
from langchain_core.tools import tool
from typing import Optional


# ---- Jira client setup ----
jira = Jira(
    url=os.environ["JIRA_INSTANCE_URL"],           # e.g. https://your-domain.atlassian.net
    username=os.environ["JIRA_USERNAME"],
    password=os.environ["JIRA_API_TOKEN"],
    cloud=True,
)


# ---- Tools ----
@tool
def get_jira_issue(issue_key: str) -> str:
    """Fetch a Jira issue by its key.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
    """
    try:
        issue = jira.issue(issue_key)
    except Exception as e:
        return f"Error fetching {issue_key}: {e}"

    fields = issue.get("fields", {})
    assignee = fields.get("assignee")
    return (
        f"Key: {issue.get('key')}\n"
        f"Summary: {fields.get('summary')}\n"
        f"Status: {fields.get('status', {}).get('name')}\n"
        f"Assignee: {assignee.get('displayName') if assignee else 'Unassigned'}"
    )


@tool
def create_jira_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
) -> str:
    """Create a new Jira issue in a given project.

    Args:
        project_key: Project key, e.g. 'PROJ'.
        summary: Issue summary/title.
        issue_type: Issue type, e.g. Task, Bug, Story.
        description: Issue description.
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
        lines.append(f"{issue['key']}: {f.get('summary')} [{f.get('status', {}).get('name')}]")
    return "\n".join(lines)


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
def transition_jira_issue(issue_key: str, transition_name: str) -> str:
    """Transition a Jira issue to a new status.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
        transition_name: Name of the target status, e.g. 'Done', 'In Progress'.
    """
    try:
        transitions = jira.get_issue_transitions(issue_key)
        match = next(
            (t for t in transitions if t["name"].lower() == transition_name.lower()),
            None,
        )
        if not match:
            available = ", ".join(t["name"] for t in transitions)
            return f"Transition '{transition_name}' not found. Available: {available}"
        jira.issue_transition(issue_key, match["name"])
    except Exception as e:
        return f"Error transitioning {issue_key}: {e}"
    return f"{issue_key} transitioned to '{transition_name}'."


@tool
def assign_jira_issue(issue_key: str, assignee: str) -> str:
    """Assign a Jira issue to a user.

    Args:
        issue_key: Jira issue key, e.g. 'PROJ-123'.
        assignee: Account ID or username to assign the issue to.
    """
    try:
        jira.assign_issue(issue_key, assignee)
    except Exception as e:
        return f"Error assigning {issue_key}: {e}"
    return f"{issue_key} assigned to {assignee}."


# All tools to bind to a model/agent
jira_tools = [
    get_jira_issue,
    create_jira_issue,
    search_jira_issues,
    add_jira_comment,
    transition_jira_issue,
    assign_jira_issue,
]