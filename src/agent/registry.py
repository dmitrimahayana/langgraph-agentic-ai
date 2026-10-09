"""Agent + skill registry persisted in the LangGraph Store.

Layout:
    ("agents",)        key=<agent name>              -> AgentSpec dict
    ("skills",)        /<skill>/SKILL.md             -> skill library (StoreBackend file)
    ("agent_files",)   /<agent>/skills/<skill>/SKILL.md -> per-agent skill copy
    ("harness_meta",)  key="seeded"                  -> first-run seed marker

The default-agent sees the library under `/skills/` and each created agent gets
`/agents/<name>/skills/` as its SkillsMiddleware source. SkillsMiddleware lists a
directory of skills, so assigning a skill copies it into the agent's folder.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import yaml
from deepagents import SubAgent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field, field_validator

from agent.model import ModelAgent
from agent.tools.catalog import TOOL_CATALOG, resolve_tools

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
base_dir = os.path.dirname(os.path.abspath(__file__))
BUNDLED_SKILLS_DIR = os.path.join(base_dir, "skills")

AGENTS_NS = ("agents",)
SKILLS_NS = ("skills",)
AGENT_FILES_NS = ("agent_files",)
META_NS = ("harness_meta",)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# deepagents ships a built-in subagent with this name
RESERVED_NAMES = {"general-purpose", "default", "default-agent"}


def validate_name(name: str) -> str:
    """Validate an agent/skill slug (lowercase letters, digits, hyphens)."""
    if not NAME_RE.match(name):
        raise ValueError(f"Invalid name {name!r}: use lowercase letters, digits and hyphens (max 64 chars).")
    return name


class AgentSpec(BaseModel):
    """A user-created agent."""

    name: str
    description: str = Field(description="What the agent does; the default-agent uses it to decide delegation.")
    system_prompt: str
    model: str = DEFAULT_MODEL
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        validate_name(v)
        if v in RESERVED_NAMES:
            raise ValueError(f"{v!r} is reserved.")
        return v

    @field_validator("tools")
    @classmethod
    def _check_tools(cls, v: list[str]) -> list[str]:
        unknown = [t for t in v if t not in TOOL_CATALOG]
        if unknown:
            raise ValueError(f"Unknown tools {unknown}. Available: {sorted(TOOL_CATALOG)}")
        return list(dict.fromkeys(v))


# ---------- Backends ----------
def skills_backend(store: BaseStore) -> StoreBackend:
    """Skill library, paths like `/<skill>/SKILL.md`."""
    return StoreBackend(store=store, namespace=lambda _rt: SKILLS_NS)


def agent_files_backend(store: BaseStore) -> StoreBackend:
    """Per-agent files, paths like `/<agent>/skills/<skill>/SKILL.md`."""
    return StoreBackend(store=store, namespace=lambda _rt: AGENT_FILES_NS)


def make_backend(store: BaseStore) -> CompositeBackend:
    """Backend for the default-agent and its subagents.

    Scratch files stay in thread state; `/skills/` and `/agents/` persist in the store.
    """
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": skills_backend(store),
            "/agents/": agent_files_backend(store),
        },
    )


# ---------- Agents ----------
async def aget_agents(store: BaseStore) -> list[AgentSpec]:
    """Return all agents, sorted by name."""
    items = await store.asearch(AGENTS_NS, limit=1000)
    specs = []
    for item in items:
        try:
            specs.append(AgentSpec(**item.value))
        except Exception as e:
            logger.warning("Skipping invalid agent %r: %s", item.key, e)
    return sorted(specs, key=lambda s: s.name)


async def aget_agent(store: BaseStore, name: str) -> AgentSpec | None:
    """Return one agent or None."""
    item = await store.aget(AGENTS_NS, name)
    return AgentSpec(**item.value) if item else None


async def aput_agent(store: BaseStore, spec: AgentSpec) -> None:
    """Create or replace an agent and sync its skill copies."""
    missing = [s for s in spec.skills if await aread_skill(store, s) is None]
    if missing:
        raise ValueError(f"Unknown skills {missing}. Create them first or pick from list_skills.")
    old = await aget_agent(store, spec.name)
    await store.aput(AGENTS_NS, spec.name, spec.model_dump())
    for skill in set(old.skills if old else []) - set(spec.skills):
        await agent_files_backend(store).adelete(f"/{spec.name}/skills/{skill}/SKILL.md")
    for skill in spec.skills:
        await _copy_skill_to_agent(store, skill, spec.name)


async def adelete_agent(store: BaseStore, name: str) -> bool:
    """Delete an agent and its skill copies. Returns False if it did not exist."""
    spec = await aget_agent(store, name)
    if spec is None:
        return False
    for skill in spec.skills:
        await agent_files_backend(store).adelete(f"/{name}/skills/{skill}/SKILL.md")
    await store.adelete(AGENTS_NS, name)
    return True


# ---------- Skills ----------
def render_skill(name: str, description: str, instructions: str) -> str:
    """Build SKILL.md content (Agent Skills format: YAML frontmatter + markdown)."""
    front = yaml.safe_dump({"name": name, "description": description}, sort_keys=False).strip()
    return f"---\n{front}\n---\n\n{instructions.strip()}\n"


def parse_skill_description(content: str) -> str:
    """Extract `description` from SKILL.md frontmatter."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return ""
    try:
        return str((yaml.safe_load(match.group(1)) or {}).get("description", ""))
    except yaml.YAMLError:
        return ""


async def aread_skill(store: BaseStore, name: str) -> str | None:
    """Return SKILL.md content of a library skill, or None."""
    result = await skills_backend(store).aread(f"/{name}/SKILL.md", limit=100_000)
    if result.error or not result.file_data:
        return None
    return result.file_data["content"]


async def alist_skills(store: BaseStore) -> dict[str, str]:
    """Return {skill name: description} for the library."""
    result = await skills_backend(store).als("/")
    skills = {}
    for entry in result.entries or []:
        name = entry["path"].strip("/").split("/")[-1]
        content = await aread_skill(store, name)
        if content is not None:
            skills[name] = parse_skill_description(content)
    return dict(sorted(skills.items()))


async def aput_skill(store: BaseStore, name: str, description: str, instructions: str) -> list[str]:
    """Create or update a library skill; re-sync agents that use it. Returns those agents."""
    validate_name(name)
    await skills_backend(store).awrite(f"/{name}/SKILL.md", render_skill(name, description, instructions))
    synced = []
    for spec in await aget_agents(store):
        if name in spec.skills:
            await _copy_skill_to_agent(store, name, spec.name)
            synced.append(spec.name)
    return synced


async def _copy_skill_to_agent(store: BaseStore, skill: str, agent: str) -> None:
    content = await aread_skill(store, skill)
    if content is not None:
        await agent_files_backend(store).awrite(f"/{agent}/skills/{skill}/SKILL.md", content)


# ---------- Seeding ----------
SEED_AGENTS = [
    ("coder", "Writes, edits, debugs and saves code in the coder workspace; can read and start Jira tickets.",
     ["save_script_file", "jira_read_ticket", "jira_start_ticket"], ["jira-workflow"]),
    ("researcher", "Researches, explains and compares topics on the internet with cited sources.",
     ["web_search"], ["web-research"]),
    ("admin", "Manages Jira: create, update, transition, assign and query issues.",
     ["jira"], ["jira-workflow"]),
]


async def aseed(store: BaseStore) -> None:
    """On first run, load bundled skills and the coder/researcher/admin agents."""
    if await store.aget(META_NS, "seeded"):
        return
    if os.path.isdir(BUNDLED_SKILLS_DIR):
        for name in sorted(os.listdir(BUNDLED_SKILLS_DIR)):
            path = os.path.join(BUNDLED_SKILLS_DIR, name, "SKILL.md")
            if os.path.isfile(path) and await aread_skill(store, name) is None:
                with open(path, encoding="utf-8") as f:
                    await skills_backend(store).awrite(f"/{name}/SKILL.md", f.read())
    for name, description, tools, skills in SEED_AGENTS:
        if await aget_agent(store, name):
            continue
        with open(os.path.join(base_dir, "souls", name, "SOUL.md"), encoding="utf-8") as f:
            soul = f.read()
        skills = [s for s in skills if await aread_skill(store, s) is not None]
        await aput_agent(store, AgentSpec(name=name, description=description, system_prompt=soul, tools=tools, skills=skills))
    await store.aput(META_NS, "seeded", {"value": True})


# ---------- Build ----------
def load_model(model_name: str) -> Any:
    """Ollama models via ModelAgent; anything else as a provider string for init_chat_model."""
    if model_name.startswith("ollama:"):
        return ModelAgent(model_name=model_name).load_model()
    return model_name


def build_subagents(specs: list[AgentSpec]) -> list[SubAgent]:
    """Turn stored specs into deepagents SubAgents."""
    return [
        SubAgent(
            name=spec.name,
            description=spec.description,
            system_prompt=spec.system_prompt,
            model=load_model(spec.model),
            tools=resolve_tools(spec.tools),
            skills=[f"/agents/{spec.name}/skills/"],
        )
        for spec in specs
    ]
