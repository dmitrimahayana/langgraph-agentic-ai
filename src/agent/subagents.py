import os, re, yaml
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools.base import BaseTool
from src.agent.catalog import catalog

BASE_DIR = Path(__file__).parent
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
SUBAGENTS_DIR = BASE_DIR / "subagents"


def is_agent_dir(path: Path) -> bool:
    """Return True when the folder has soul/SOUL.md."""
    return (path / "soul" / "SOUL.md").is_file()


def load_agent(path: Path, model: BaseChatModel, tools: list[str] = None) -> dict:
    """Read one agent folder."""
    soul_path = path / "soul" / "SOUL.md"
    meta, prompt = split_frontmatter(soul_path.read_text(encoding="utf-8"))

    agent_dict = {
        "name": path.name,
        "description": str(meta.get("description", "")),
        "system_prompt": prompt,
        "model": model,
    }

    # Resolve tool names using the ToolCatalog
    if tools:
        agent_dict["tools"] = catalog.resolve(tools)

    # Load skills from src/agent/subagents/<agent>/skills/
    skills_dir = path / "skills"
    skills = []
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.is_file():
                    skills.append(skill_file.read_text(encoding="utf-8").strip())
    
    if skills:
        agent_dict["skills"] = skills

    return agent_dict

# ---------- Markdown formats ----------
def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[match.end():].lstrip("\n")

def list_agents() -> list:
    root = SUBAGENTS_DIR
    subagents = []
    if not root.is_dir():
        return subagents
        
    for path in sorted(root.iterdir()):
        if path.is_dir() and NAME_RE.match(path.name) and is_agent_dir(path):
            try:
                # Note: list_agents usually doesn't have model/tools, 
                # but load_agent requires model. This might need a default or change.
                subagents.append(load_agent(path, model=None))
            except Exception as e:
                print(f"Skipping agent folder {path}: {e}")
    return subagents

# ---------- Markdown formats ----------
def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[match.end():].lstrip("\n")

def list_agents() -> list:
    root = SUBAGENTS_DIR
    subagents = []
    if not root.is_dir():
        return subagents
        
    for path in sorted(root.iterdir()):
        if path.is_dir() and NAME_RE.match(path.name) and is_agent_dir(path):
            try:
                # Note: list_agents usually doesn't have model/tools, 
                # but load_agent requires model. This might need a default or change.
                subagents.append(load_agent(path, model=None))
            except Exception as e:
                print(f"Skipping agent folder {path}: {e}")
    return subagents