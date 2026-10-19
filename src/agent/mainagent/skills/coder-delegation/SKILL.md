---
name: coder-delegation
description: Workflow for handling Coding Task.
---

# Coder Delegation Skill

This skill defines the workflow for delegating technical implementation, bug fixing, and code refactoring tasks to the `coder` subagent.

## When to use this skill
- When a task requires writing complex logic, implementing a feature, or fixing a bug.
- When the task involves multiple files or requires deep architectural knowledge of the codebase.
- When you need a specialized agent focused on code quality, testing, and implementation.

## Workflow
1. **Analyze the Requirement**: Clearly define the goal, constraints, and expected output of the coding task.
2. **Gather Context**: Use `ls`, `read_file`, and `grep` to find all relevant files and existing patterns in the codebase.
3. **Invoke Coder Agent**: Use the `task` tool with `subagent_type="coder"`.
4. **Provide a Comprehensive Prompt**:
    - **Goal**: What exactly needs to be built or fixed.
    - **Context**: Paths to relevant files and a summary of the current implementation.
    - **Requirements**: Specific constraints (e.g., "must handle rate limiting", "use async/await").
    - **Expected Output**: Whether the agent should provide a full file, a diff, or a specific implementation plan.
5. **Review and Integrate**: Review the code produced by the coder agent and apply it using `write_file` or `edit_file`.

## Example Prompt for Coder Agent
"Implement a Python scraper for Semantic Scholar API. 
Goal: Extract titles and abstracts for 'cybersecurity' papers.
Requirements: 
- Handle HTTP 429 rate limits using the 'Retry-After' header.
- Implement pagination to fetch up to 500 results.
- Save output to CSV.
Relevant Files: [list of files]
Please provide the complete implementation in a single file named `scraper.py`."
