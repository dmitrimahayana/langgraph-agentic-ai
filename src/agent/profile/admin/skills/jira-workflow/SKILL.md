---
name: jira-workflow
description: Team conventions for reading, starting, moving and assigning Jira tickets, including the review process.
---

---
name: jira-workflow
description: Team conventions for reading, starting, moving and assigning Jira tickets.
---

# Jira Workflow

## Rules
- Always read the ticket before acting on it (summary, description, status, assignee).
- Whenever a ticket changes status, assign it to the bot's own Jira account in the same step.
- Status flow: To Do → In Progress → Review → Done. Never skip In Progress.
- When moving a ticket to **Review**:
    1. Transition the ticket status to "Review".
    2. Add a comment mentioning @dmitri to notify them that the implementation is ready.
    3. Assign the ticket to `dmitri.mahayana`.
- Report back: ticket key, old → new status, assignee, and anything blocking.

## Errors
If a Jira call fails, report the exact error as a blocker instead of guessing.
