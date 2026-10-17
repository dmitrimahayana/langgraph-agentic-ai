---
name: working-on-jira
description: Workflow for handling Jira tickets.
---

# Working on Jira Ticket Workflow

When assigned a Jira ticket or tasked to resolve one, follow these steps:

1. **Analyze Ticket**: Use `get_jira_issue` to read the ticket description and understand the requirements, goals, and context.
2. **Explore Subtasks**: Use `get_jira_subtasks` to identify if there are already existing subtasks and understand the current breakdown of work.
3. **Update Status**: Use `transition_jira_issue` to move the ticket status to "In Progress" (or the equivalent transition in the project workflow) to signal that work has started.
4. **Plan Execution**: If necessary, create additional subtasks using `create_jira_subtask` to break down the remaining work.
5. **Execute and Document**: As work progresses, add comments via `add_jira_comment` to provide updates.
6. **Close Ticket**: Once the work is completed and verified, use `close_jira_issue` to move the ticket to a "Done" or "Resolved" status.
