---
name: jira-workflow
description: REQUIRED for any task that mentions a Jira ticket key (e.g. PP-3). Read ticket, start it, implement in /workspace/, then hand it to the reviewer (In Review + comment mentioning dmitri + assign to dmitri).
---

# Jira Workflow

When a task references a Jira ticket (e.g. "take PP-3 and implement it"), run **all** steps in order. A ticket task is not finished until step 4 succeeds.

## Steps
1. **Read** — call `get_jira_ticket` with the issue key to get the requirements. Never ask the user for ticket details before trying this.
2. **Start** — call `start_jira_ticket`. It assigns the ticket to the bot's own Jira account and moves it to **In Progress**.
3. **Implement** — write the code under `/workspace/<ticket-key-lowercase>/` (e.g. `/workspace/pp-3/`) with `write_file` / `edit_file`.
4. **Hand to review** — call `submit_jira_ticket_for_review` with:
   - `reviewer`: `dmitri`
   - `comment`: what was implemented, the files changed under `/workspace/`, and how to run/test it

   This one call moves the ticket to **In Review**, adds the comment mentioning @dmitri, and assigns the ticket to dmitri.

## Rules
- Status flow: To Do → In Progress → In Review → Done. Never skip In Progress.
- The coder never moves a ticket to **Done** — the reviewer does.
- Do not change status or assignee with any other tool; only `start_jira_ticket` and `submit_jira_ticket_for_review`.

## Report
Report back: ticket key, old → new status, assignee, files changed, and anything blocking.

## Errors
If a Jira call fails, report the exact tool error as a blocker, including which steps already succeeded. Do not guess or retry with different status names.
