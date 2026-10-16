import os, re, yaml
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
# from src.agent.catalog import catalog
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend

BASE_DIR = Path(__file__).parent
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
SUBAGENTS_DIR = BASE_DIR / "subagents"
WORKSPACE_DIR = BASE_DIR.parent / "workspace"


def is_agent_dir(path: Path) -> bool:
    """Return True when the folder has soul/SOUL.md."""
    return (path / "soul" / "SOUL.md").is_file()


def load_agent(path: Path, model: BaseChatModel) -> dict:
    """Read one agent folder."""
    soul_path = path / "soul" / "SOUL.md"
    meta, prompt = split_frontmatter(soul_path.read_text(encoding="utf-8"))

    agent_dict = {
        "name": path.name,
        "description": str(meta.get("description", "")),
        "system_prompt": prompt,
        "model": model,
    }

    # Load tools from src/agent/subagents/<agent>/tools/
    tools_dir = path / "tools"
    tool_names = []
    tool_descriptions = {}
    if tools_dir.is_dir():
        for tool_dir in tools_dir.iterdir():
            if tool_dir.is_dir():
                tool_file = tool_dir / "TOOL.md"
                if tool_file.is_file():
                    content = tool_file.read_text(encoding="utf-8")
                    t_meta, _ = split_frontmatter(content)
                    name = t_meta.get("name")
                    description = t_meta.get("description")
                    if name:
                        tool_names.append(name)
                        if description:
                            tool_descriptions[name] = description
    
    if tool_names:
        agent_dict["tools"] = catalog.resolve(tool_names, descriptions=tool_descriptions)

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

    # Implement Composite Backend for Deep Agent filesystem access
    # Default: StateBackend (ephemeral storage for internal agent data)
    # Routes: /skills/ -> agent skills folder, /workspace/ -> global workspace
    routes = {}
    if skills_dir.is_dir():
        routes["/skills/"] = FilesystemBackend(root_dir=str(skills_dir), virtual_mode=True)
    
    if WORKSPACE_DIR.is_dir():
        routes["/workspace/"] = FilesystemBackend(root_dir=str(WORKSPACE_DIR), virtual_mode=True)

    agent_dict["backend"] = CompositeBackend(
        default=StateBackend(),
        routes=routes
    )

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
                subagents.append(load_agent(path, model=None))
            except Exception as e:
                print(f"Skipping agent folder {path}: {e}")
    return subagents

if __name__ == "__main__":
    import pprint
    import sys
    from pathlib import Path
    
    # Add the project root to sys.path so 'src' can be found when running this file directly
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    from src.agent.catalog import catalog
    
    print("Listing all discovered subagents...")
    try:
        agents = list_agents()
        pprint.pprint(agents)
        print(f"\nTotal agents found: {len(agents)}")
    except Exception as e:
        print(f"Error during testing: {e}")
