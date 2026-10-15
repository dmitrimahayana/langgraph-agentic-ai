import os, re, yaml
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools.base import BaseTool

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = BASE_DIR / "src" / "core"


def is_agent_dir(path: Path) -> bool:
    """Return True when the folder has souls/SOUL.md."""
    return (path / "souls" / "SOUL.md").is_file()

def load_agent(path: Path, model: BaseChatModel, tools: list[BaseTool]) -> dict:
    """Read one agent folder."""
    meta, prompt = split_frontmatter((path / "souls" / "SOUL.md").read_text(encoding="utf-8"))
    
    agent_dict = {
        "name": path.name,
        "description": str(meta.get("description", "")),
        "system_prompt": prompt,
        "model": model,
    }
    
    if tools:
        agent_dict["tools"] = tools
        
    skills_file = path / "skills"
    if skills_file.is_file():
        skills_content = skills_file.read_text(encoding="utf-8").strip()
        if skills_content:
            agent_dict["skills"] = skills_content
            
    return agent_dict

# ---------- Markdown formats ----------
def split_frontmatter(text: str) -> tuple[dict[str], str]:
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
    root = Path(PROFILE_DIR)
    specs = []
    for path in sorted(root.iterdir()) if root.is_dir() else []:
        if path.is_dir() and NAME_RE.match(path.name) and is_agent_dir(path):
            try:
                specs.append(load_agent(path))
            except Exception as e:
                print("Skipping agent folder %s: %s", path, e)
    return specs