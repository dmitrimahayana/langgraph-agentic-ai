---
name: jira-workflow
description: Team conventions for reading, starting, moving and assigning Jira tickets.
---

# Jira Workflow

## Rules
- Always read the ticket before acting on it (summary, description, status, assignee).
- Whenever a ticket changes status, assign it to the bot's own Jira account in the same step.
- Status flow: To Do → In Progress → Done. Never skip In Progress.
- Report back: ticket key, old → new status, assignee, and anything blocking.

## Errors
If a Jira call fails, report the exact error as a blocker instead of guessing.
