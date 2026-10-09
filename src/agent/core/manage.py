"""Management tools for the default agent: create agent folders, skills, assign tools.

Tools are sync on purpose: LangChain runs them in a worker thread, so the
registry's file I/O never blocks the event loop.
"""

from __future__ import annotations

from langchain.tools import tool
from pydantic import ValidationError

from agent import registry
from agent.core.catalog import TOOL_CATALOG

NEXT_TURN_NOTE = "It takes effect from the user's next message."


def _errors(e: ValidationError | ValueError) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(err["msg"] for err in e.errors())
    return str(e)


@tool
def list_tools() -> str:
    """List the tools that can be assigned to agents."""
    return "\n".join(f"- {name}: {entry.description}" for name, entry in TOOL_CATALOG.items())


@tool
def list_agents() -> str:
    """List all agents with their model, tools and skills."""
    specs = registry.list_agents()
    if not specs:
        return "No agents yet."
    return "\n".join(
        f"- {s.name}: {s.description}\n  model={s.model} tools={s.tools} skills={s.skills}"
        for s in specs
    )


@tool
def get_agent(name: str) -> str:
    """Show an agent's full configuration including its system prompt.

    Args:
        name: Agent name
    """
    try:
        spec = registry.get_agent(name)
    except ValueError as e:
        return f"Error: {e}"
    return spec.model_dump_json(indent=2) if spec else f"Agent {name!r} not found."


@tool
def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list[str] | None = None,
    model: str | None = None,
) -> str:
    """Create a new agent folder (souls/SOUL.md, tools/TOOLS.md, skills/). Add skills afterwards with save_skill or copy_skill.

    Args:
        name: Agent slug, lowercase letters, digits and hyphens, e.g. "release-manager"
        description: What the agent does; used to decide when to delegate to it
        system_prompt: The agent's persona and instructions
        tools: Tool names from list_tools
        model: Model id like "ollama:gemma4:31b-cloud"; omit for the default
    """
    try:
        if registry.get_agent(name):
            return f"Error: agent {name!r} already exists. Use update_agent."
        spec = registry.AgentSpec(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools or [],
            model=model or registry.DEFAULT_MODEL,
        )
        path = registry.save_agent(spec)
    except (ValidationError, ValueError) as e:
        return f"Error: {_errors(e)}"
    return f"Agent {name!r} created at {path}. {NEXT_TURN_NOTE}"


@tool
def update_agent(
    name: str,
    description: str | None = None,
    system_prompt: str | None = None,
    tools: list[str] | None = None,
    model: str | None = None,
) -> str:
    """Update an agent's SOUL.md / TOOLS.md. Only given fields change; tools replaces the whole list.

    Args:
        name: Agent name
        description: New description
        system_prompt: New system prompt
        tools: Full new list of tool names
        model: New model id
    """
    try:
        spec = registry.get_agent(name)
        if spec is None:
            return f"Error: agent {name!r} not found."
        changes = {
            k: v
            for k, v in {
                "description": description,
                "system_prompt": system_prompt,
                "tools": tools,
                "model": model,
            }.items()
            if v is not None
        }
        registry.save_agent(registry.AgentSpec(**{**spec.model_dump(), **changes}))
    except (ValidationError, ValueError) as e:
        return f"Error: {_errors(e)}"
    return f"Agent {name!r} updated ({', '.join(changes) or 'no changes'}). {NEXT_TURN_NOTE}"


@tool
def delete_agent(name: str) -> str:
    """Delete an agent folder. Only call after the user explicitly confirmed the deletion.

    Args:
        name: Agent name
    """
    try:
        deleted = registry.delete_agent(name)
    except ValueError as e:
        return f"Error: {e}"
    return f"Agent {name!r} deleted." if deleted else f"Error: agent {name!r} not found."


@tool
def list_skills(agent: str | None = None) -> str:
    """List skills per agent.

    Args:
        agent: Only this agent's skills; omit for all agents
    """
    try:
        names = [agent] if agent else [s.name for s in registry.list_agents()]
        lines = []
        for name in names:
            for skill, desc in registry.list_skills(name).items():
                lines.append(f"- {name}/{skill}: {desc}")
    except ValueError as e:
        return f"Error: {e}"
    return "\n".join(lines) or "No skills yet."


@tool
def read_skill(agent: str, skill: str) -> str:
    """Show the full SKILL.md of an agent's skill.

    Args:
        agent: Agent name
        skill: Skill name
    """
    try:
        content = registry.read_skill(agent, skill)
    except ValueError as e:
        return f"Error: {e}"
    return content if content is not None else f"Skill {agent}/{skill} not found."


@tool
def save_skill(agent: str, skill: str, description: str, instructions: str) -> str:
    """Create or update a skill in an agent's skills/ folder.

    Args:
        agent: Agent that gets the skill
        skill: Skill slug, lowercase letters, digits and hyphens, e.g. "release-notes"
        description: One line saying what the skill does and when to use it
        instructions: Markdown body: step-by-step procedure, conventions, examples
    """
    try:
        path = registry.save_skill(agent, skill, description, instructions)
    except ValueError as e:
        return f"Error: {e}"
    return f"Skill saved at {path}. {NEXT_TURN_NOTE}"


@tool
def copy_skill(skill: str, from_agent: str, to_agent: str) -> str:
    """Copy a skill folder from one agent to another.

    Args:
        skill: Skill name
        from_agent: Agent that has the skill
        to_agent: Agent that should get it
    """
    try:
        path = registry.copy_skill(skill, from_agent, to_agent)
    except ValueError as e:
        return f"Error: {e}"
    return f"Skill copied to {path}. {NEXT_TURN_NOTE}"


@tool
def delete_skill(agent: str, skill: str) -> str:
    """Remove a skill from an agent. Only call after the user confirmed.

    Args:
        agent: Agent name
        skill: Skill name
    """
    try:
        deleted = registry.delete_skill(agent, skill)
    except ValueError as e:
        return f"Error: {e}"
    return f"Skill {agent}/{skill} deleted." if deleted else f"Error: skill {agent}/{skill} not found."


MANAGEMENT_TOOLS = [
    list_tools,
    list_agents,
    get_agent,
    create_agent,
    update_agent,
    delete_agent,
    list_skills,
    read_skill,
    save_skill,
    copy_skill,
    delete_skill,
]
