"""Management tools for the default-agent: create agents, skills, assign tools."""

from __future__ import annotations

from langchain.tools import ToolRuntime, tool
from pydantic import ValidationError

from agent import registry
from agent.tools.catalog import TOOL_CATALOG

NEXT_TURN_NOTE = "It can be delegated to from the user's next message."


def _errors(e: ValidationError | ValueError) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(err["msg"] for err in e.errors())
    return str(e)


@tool
def list_tools() -> str:
    """List the tools that can be assigned to agents."""
    return "\n".join(f"- {name}: {entry.description}" for name, entry in TOOL_CATALOG.items())


@tool
async def list_skills(runtime: ToolRuntime) -> str:
    """List the skills in the skill library."""
    skills = await registry.alist_skills(runtime.store)
    if not skills:
        return "No skills yet."
    return "\n".join(f"- {name}: {desc}" for name, desc in skills.items())


@tool
async def read_skill(name: str, runtime: ToolRuntime) -> str:
    """Show the full SKILL.md of a library skill.

    Args:
        name: Skill name
    """
    content = await registry.aread_skill(runtime.store, name)
    return content if content is not None else f"Skill {name!r} not found."


@tool
async def save_skill(name: str, description: str, instructions: str, runtime: ToolRuntime) -> str:
    """Create or update a skill in the library. Agents that have it get the new version.

    Args:
        name: Skill slug, lowercase letters, digits and hyphens, e.g. "release-notes"
        description: One line saying what the skill does and when to use it
        instructions: Markdown body: step-by-step procedure, conventions, examples
    """
    try:
        synced = await registry.aput_skill(runtime.store, name, description, instructions)
    except ValueError as e:
        return f"Error: {_errors(e)}"
    suffix = f" Updated for agents: {', '.join(synced)}." if synced else ""
    return f"Skill {name!r} saved.{suffix}"


@tool
async def list_agents(runtime: ToolRuntime) -> str:
    """List created agents with their model, tools and skills."""
    specs = await registry.aget_agents(runtime.store)
    if not specs:
        return "No agents yet."
    return "\n".join(
        f"- {s.name}: {s.description}\n  model={s.model} tools={s.tools} skills={s.skills}"
        for s in specs
    )


@tool
async def get_agent(name: str, runtime: ToolRuntime) -> str:
    """Show an agent's full configuration including its system prompt.

    Args:
        name: Agent name
    """
    spec = await registry.aget_agent(runtime.store, name)
    return spec.model_dump_json(indent=2) if spec else f"Agent {name!r} not found."


@tool
async def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    runtime: ToolRuntime,
    tools: list[str] | None = None,
    skills: list[str] | None = None,
    model: str | None = None,
) -> str:
    """Create a new agent.

    Args:
        name: Agent slug, lowercase letters, digits and hyphens, e.g. "release-manager"
        description: What the agent does; used to decide when to delegate to it
        system_prompt: The agent's persona and instructions
        tools: Tool names from list_tools
        skills: Skill names from list_skills
        model: Model id like "ollama:gemma4:31b-cloud"; omit for the default
    """
    if await registry.aget_agent(runtime.store, name):
        return f"Error: agent {name!r} already exists. Use update_agent."
    try:
        spec = registry.AgentSpec(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools or [],
            skills=skills or [],
            model=model or registry.DEFAULT_MODEL,
        )
        await registry.aput_agent(runtime.store, spec)
    except (ValidationError, ValueError) as e:
        return f"Error: {_errors(e)}"
    return f"Agent {name!r} created. {NEXT_TURN_NOTE}"


@tool
async def update_agent(
    name: str,
    runtime: ToolRuntime,
    description: str | None = None,
    system_prompt: str | None = None,
    tools: list[str] | None = None,
    skills: list[str] | None = None,
    model: str | None = None,
) -> str:
    """Update an agent. Only given fields change; tools and skills replace the whole list.

    Args:
        name: Agent name
        description: New description
        system_prompt: New system prompt
        tools: Full new list of tool names
        skills: Full new list of skill names
        model: New model id
    """
    spec = await registry.aget_agent(runtime.store, name)
    if spec is None:
        return f"Error: agent {name!r} not found."
    changes = {
        k: v
        for k, v in {
            "description": description,
            "system_prompt": system_prompt,
            "tools": tools,
            "skills": skills,
            "model": model,
        }.items()
        if v is not None
    }
    try:
        updated = registry.AgentSpec(**{**spec.model_dump(), **changes})
        await registry.aput_agent(runtime.store, updated)
    except (ValidationError, ValueError) as e:
        return f"Error: {_errors(e)}"
    return f"Agent {name!r} updated ({', '.join(changes) or 'no changes'}). {NEXT_TURN_NOTE}"


@tool
async def delete_agent(name: str, runtime: ToolRuntime) -> str:
    """Delete an agent. Only call after the user explicitly confirmed the deletion.

    Args:
        name: Agent name
    """
    if await registry.adelete_agent(runtime.store, name):
        return f"Agent {name!r} deleted."
    return f"Error: agent {name!r} not found."


MANAGEMENT_TOOLS = [
    list_tools,
    list_skills,
    read_skill,
    save_skill,
    list_agents,
    get_agent,
    create_agent,
    update_agent,
    delete_agent,
]
