"""File-based agent registry: one folder per agent.

Layout (`src/agent/profile/`, the single source of truth):

    <agent-name>/
        souls/SOUL.md              frontmatter (name, description, model) + system prompt
        tools/TOOLS.md             catalog tool names, one `- name` line each
        skills/<skill>/SKILL.md    Agent Skills format (frontmatter + instructions)

A folder is an agent when it has `souls/SOUL.md`. The `default` agent is the
chat entry point; every other agent is a subagent it can delegate to.

All functions here do blocking file I/O: call them from sync tools or via
`asyncio.to_thread` (langgraph dev rejects blocking calls on the event loop).
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from deepagents import FilesystemPermission, SubAgent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from langchain.agents.middleware import ModelRetryMiddleware
from pydantic import BaseModel, Field, field_validator

from agent.core.catalog import (
    TOOL_CATALOG,
    WORKSPACE_DIR,
    WORKSPACE_TOOL,
    resolve_tools,
)
from agent.model import ModelAgent

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ollama:gemma4:31b-cloud"
DEFAULT_AGENT = "default"
# The one and only agents directory
PROFILE_DIR = Path(__file__).resolve().parent / "profile"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# deepagents ships a built-in `general-purpose` subagent
RESERVED_NAMES = {"general-purpose"}
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
TOOL_LINE_RE = re.compile(r"^\s*[-*]\s+`?([a-z0-9_]+)`?", re.MULTILINE)


def agents_dir() -> Path:
    """Root folder holding agent folders."""
    return PROFILE_DIR


def validate_name(name: str) -> str:
    """Validate an agent/skill slug; also blocks path traversal."""
    if not NAME_RE.match(name):
        raise ValueError(f"Invalid name {name!r}: use lowercase letters, digits and hyphens (max 64 chars).")
    return name


def agent_path(name: str) -> Path:
    """Folder of an agent (may not exist)."""
    return agents_dir() / validate_name(name)


def is_agent_dir(path: Path) -> bool:
    """Return True when the folder has souls/SOUL.md."""
    return (path / "souls" / "SOUL.md").is_file()


# ---------- Markdown formats ----------
def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[match.end():].lstrip("\n")


def with_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Render `---` YAML frontmatter followed by a markdown body."""
    front = yaml.safe_dump(meta, sort_keys=False, width=10_000).strip()
    return f"---\n{front}\n---\n\n{body.strip()}\n"


def parse_tools_md(text: str) -> list[str]:
    """Tool names from `- name` list lines (text after the name is ignored)."""
    return list(dict.fromkeys(TOOL_LINE_RE.findall(text)))


def render_tools_md(tools: list[str]) -> str:
    """Render TOOLS.md with a description comment per tool."""
    lines = [f"- {t}  <!-- {TOOL_CATALOG[t].description} -->" for t in tools]
    body = "\n".join(lines) or "<!-- none: add catalog tool names as '- name' lines -->"
    return f"# Tools\n\nOne catalog tool name per line (see src/agent/core/catalog.py).\n\n{body}\n"


# ---------- Agents ----------
class AgentSpec(BaseModel):
    """An agent folder, loaded into memory."""

    name: str
    description: str = Field(description="What the agent does; the default agent uses it to decide delegation.")
    system_prompt: str
    model: str = DEFAULT_MODEL
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="Read from skills/; not written by save_agent.")

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


def load_agent(path: Path) -> AgentSpec:
    """Read one agent folder."""
    meta, prompt = split_frontmatter((path / "souls" / "SOUL.md").read_text(encoding="utf-8"))
    tools_md = path / "tools" / "TOOLS.md"
    tools = parse_tools_md(tools_md.read_text(encoding="utf-8")) if tools_md.is_file() else []
    unknown = [t for t in tools if t not in TOOL_CATALOG]
    if unknown:
        logger.warning("Agent %r: unknown tools %s skipped", path.name, unknown)
    return AgentSpec(
        name=path.name,
        description=str(meta.get("description", "")),
        system_prompt=prompt,
        model=str(meta.get("model") or DEFAULT_MODEL),
        tools=[t for t in tools if t in TOOL_CATALOG],
        skills=list(list_skills(path.name)),
    )


def list_agents() -> list[AgentSpec]:
    """All agent folders (including `default`), sorted by name. Broken folders are skipped."""
    root = agents_dir()
    specs = []
    for path in sorted(root.iterdir()) if root.is_dir() else []:
        if path.is_dir() and NAME_RE.match(path.name) and is_agent_dir(path):
            try:
                specs.append(load_agent(path))
            except Exception as e:
                logger.warning("Skipping agent folder %s: %s", path, e)
    return specs


def get_agent(name: str) -> AgentSpec | None:
    """One agent, or None."""
    path = agent_path(name)
    return load_agent(path) if is_agent_dir(path) else None


def save_agent(spec: AgentSpec) -> Path:
    """Create or overwrite an agent's SOUL.md and TOOLS.md; ensures skills/ exists."""
    path = agent_path(spec.name)
    for sub in ("souls", "tools", "skills"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    meta = {"name": spec.name, "description": spec.description, "model": spec.model}
    (path / "souls" / "SOUL.md").write_text(with_frontmatter(meta, spec.system_prompt), encoding="utf-8")
    (path / "tools" / "TOOLS.md").write_text(render_tools_md(spec.tools), encoding="utf-8")
    return path


def delete_agent(name: str) -> bool:
    """Delete an agent folder. The default agent cannot be deleted."""
    if name == DEFAULT_AGENT:
        raise ValueError("The default agent cannot be deleted.")
    path = agent_path(name)
    if name in RESERVED_NAMES or not is_agent_dir(path):
        return False
    shutil.rmtree(path)
    return True


# ---------- Skills ----------
def skill_path(agent: str, skill: str) -> Path:
    """SKILL.md path of an agent's skill (may not exist)."""
    return agent_path(agent) / "skills" / validate_name(skill) / "SKILL.md"


def list_skills(agent: str) -> dict[str, str]:
    """{skill name: description} for one agent."""
    root = agent_path(agent) / "skills"
    skills = {}
    for path in sorted(root.iterdir()) if root.is_dir() else []:
        skill_md = path / "SKILL.md"
        if skill_md.is_file():
            meta, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
            skills[path.name] = str(meta.get("description", ""))
    return skills


def read_skill(agent: str, skill: str) -> str | None:
    """Full SKILL.md, or None."""
    path = skill_path(agent, skill)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def save_skill(agent: str, skill: str, description: str, instructions: str) -> Path:
    """Create or overwrite a skill in an agent's skills/ folder."""
    if get_agent(agent) is None:
        raise ValueError(f"Agent {agent!r} not found.")
    path = skill_path(agent, skill)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(with_frontmatter({"name": skill, "description": description}, instructions), encoding="utf-8")
    return path


def copy_skill(skill: str, from_agent: str, to_agent: str) -> Path:
    """Copy a whole skill folder (SKILL.md + supporting files) to another agent."""
    src = skill_path(from_agent, skill).parent
    if not (src / "SKILL.md").is_file():
        raise ValueError(f"Skill {skill!r} not found in agent {from_agent!r}.")
    if get_agent(to_agent) is None:
        raise ValueError(f"Agent {to_agent!r} not found.")
    dst = skill_path(to_agent, skill).parent
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def delete_skill(agent: str, skill: str) -> bool:
    """Delete one skill folder from an agent."""
    path = skill_path(agent, skill).parent
    if not path.is_dir():
        return False
    shutil.rmtree(path)
    return True


# ---------- Build ----------
def model_middleware() -> list[Any]:
    """Per-agent model middleware: retry timed-out / failed model calls instead of failing the run."""
    return [ModelRetryMiddleware(max_retries=2)]


def load_model(model_name: str) -> Any:
    """Ollama models via ModelAgent; anything else as a provider string for init_chat_model."""
    if model_name.startswith("ollama:"):
        return ModelAgent(model_name=model_name).load_model()
    return model_name


def skills_source(name: str) -> str:
    """Virtual path SkillsMiddleware reads an agent's skills from."""
    return f"/agents/{name}/skills/"


WORKSPACE_PATH = "/workspace/"


def make_backend(specs: list[AgentSpec]) -> CompositeBackend:
    """Route virtual paths to storage.

    /workspace/              -> WORKSPACE_DIR (repos + code output)
    /agents/<name>/skills/   -> src/agent/profile/<name>/skills/
    anything else            -> thread state (scratch, discarded after the turn)

    SOUL.md, TOOLS.md and code are never mounted. Who may use which path is
    decided per agent by permissions_for().
    """
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    routes: dict[str, Any] = {WORKSPACE_PATH: FilesystemBackend(root_dir=WORKSPACE_DIR, virtual_mode=True)}
    root = agents_dir()
    for s in specs:
        routes[skills_source(s.name)] = FilesystemBackend(root_dir=root / s.name / "skills", virtual_mode=True)
    return CompositeBackend(default=StateBackend(), routes=routes)


def permissions_for(spec: AgentSpec) -> list[FilesystemPermission]:
    """File access rules for one agent (first match wins).

    - may write only its own skills/ folder, not other agents'
    - may touch /workspace/ only with `workspace` in TOOLS.md
    """
    rules = [
        FilesystemPermission(operations=["write"], paths=[f"{skills_source(spec.name)}**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/agents/**"], mode="deny"),
    ]
    if WORKSPACE_TOOL not in spec.tools:
        rules.append(
            FilesystemPermission(operations=["read", "write"], paths=["/workspace", f"{WORKSPACE_PATH}**"], mode="deny")
        )
    return rules


def build_subagents(specs: list[AgentSpec]) -> list[SubAgent]:
    """Turn agent folders into deepagents SubAgents."""
    return [
        SubAgent(
            name=spec.name,
            description=spec.description,
            system_prompt=spec.system_prompt,
            model=load_model(spec.model),
            tools=resolve_tools(spec.tools),
            skills=[skills_source(spec.name)],
            permissions=permissions_for(spec),
            middleware=model_middleware(),
        )
        for spec in specs
    ]
