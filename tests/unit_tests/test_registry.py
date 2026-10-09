"""Unit tests for the folder-based agent registry and management tools."""

import sys
from unittest.mock import Mock

import pytest
from deepagents.middleware.filesystem import _check_fs_permission
from deepagents.middleware.skills import _alist_skills
from langchain_core.messages import AIMessage, HumanMessage

from agent import registry
from agent.core import manage

pytestmark = pytest.mark.anyio


def run(tool, **kwargs):
    return tool.invoke(kwargs)


def test_reads_profile_folders(agents_dir):
    names = [s.name for s in registry.list_agents()]
    assert names == ["admin", "coder", "default", "researcher", "slack"]
    coder = registry.get_agent("coder")
    assert coder.tools == ["workspace", "jira_read_ticket", "jira_start_ticket", "jira_submit_review"]
    assert coder.skills == ["jira-workflow"]
    assert coder.system_prompt.startswith("# Profile: Coder")


def test_ignores_non_agent_folders(agents_dir):
    (agents_dir / "notes").mkdir()
    (agents_dir / "__pycache__").mkdir(exist_ok=True)
    assert "notes" not in [s.name for s in registry.list_agents()]


def test_create_agent_writes_folder(agents_dir):
    out = run(manage.create_agent, name="pm", description="Project manager", system_prompt="You are PM.", tools=["jira"])
    assert "created" in out
    assert (agents_dir / "pm/souls/SOUL.md").read_text().startswith("---\nname: pm\n")
    assert "- jira" in (agents_dir / "pm/tools/TOOLS.md").read_text()
    assert (agents_dir / "pm/skills").is_dir()
    spec = registry.get_agent("pm")
    assert (spec.description, spec.system_prompt.strip(), spec.tools) == ("Project manager", "You are PM.", ["jira"])


def test_create_agent_rejects_bad_input(agents_dir):
    assert "rm_rf" in run(manage.create_agent, name="x", description="d", system_prompt="p", tools=["rm_rf"])
    assert run(manage.create_agent, name="Bad Name", description="d", system_prompt="p").startswith("Error")
    assert run(manage.create_agent, name="general-purpose", description="d", system_prompt="p").startswith("Error")
    assert run(manage.create_agent, name="coder", description="d", system_prompt="p").startswith("Error")
    assert run(manage.get_agent, name="../etc").startswith("Error")
    assert not (agents_dir / "x").exists()


def test_hand_edited_tools_md_is_read(agents_dir):
    (agents_dir / "researcher/tools/TOOLS.md").write_text("# Tools\n\n- web_search\n- `slack` because why not\n- bogus\n")
    assert registry.get_agent("researcher").tools == ["web_search", "slack"]


def test_skills_save_copy_delete(agents_dir):
    run(manage.create_agent, name="pm", description="d", system_prompt="p")
    assert "saved" in run(manage.save_skill, agent="pm", skill="release-notes", description="Write notes", instructions="1. Do it")
    assert "copied" in run(manage.copy_skill, skill="release-notes", from_agent="pm", to_agent="coder")
    assert registry.get_agent("coder").skills == ["jira-workflow", "release-notes"]
    assert "pm/release-notes: Write notes" in run(manage.list_skills)
    assert "deleted" in run(manage.delete_skill, agent="coder", skill="release-notes")
    assert registry.get_agent("coder").skills == ["jira-workflow"]


async def test_skills_middleware_reads_agent_folder(agents_dir):
    backend = registry.make_backend(registry.list_agents())
    skills = await _alist_skills(backend, registry.skills_source("researcher"))
    assert [s["name"] for s in skills] == ["web-research"]


def test_delete_agent(agents_dir):
    run(manage.create_agent, name="pm", description="d", system_prompt="p")
    assert "deleted" in run(manage.delete_agent, name="pm")
    assert not (agents_dir / "pm").exists()
    assert run(manage.delete_agent, name="pm").startswith("Error")
    assert run(manage.delete_agent, name="default").startswith("Error")


def test_workspace_permissions(agents_dir):
    coder = registry.permissions_for(registry.get_agent("coder"))
    researcher = registry.permissions_for(registry.get_agent("researcher"))
    assert _check_fs_permission(coder, "write", "/workspace/pp-1/main.py") == "allow"
    assert _check_fs_permission(researcher, "write", "/workspace/pp-1/main.py") == "deny"
    assert _check_fs_permission(researcher, "read", "/workspace") == "deny"


def test_agents_write_only_own_skills(agents_dir):
    coder = registry.permissions_for(registry.get_agent("coder"))
    assert _check_fs_permission(coder, "write", "/agents/coder/skills/x/SKILL.md") == "allow"
    assert _check_fs_permission(coder, "write", "/agents/admin/skills/x/SKILL.md") == "deny"
    assert _check_fs_permission(coder, "read", "/agents/admin/skills/x/SKILL.md") == "allow"


async def test_workspace_backend_maps_to_dir(agents_dir):
    backend = registry.make_backend(registry.list_agents())
    await backend.awrite("/workspace/pp-1/main.py", "print(1)")
    assert (registry.WORKSPACE_DIR / "pp-1/main.py").read_text() == "print(1)"


def test_build_subagents_shape(agents_dir):
    (sub,) = registry.build_subagents([registry.get_agent("coder")])
    assert sub["name"] == "coder"
    assert [t.name for t in sub["tools"]] == ["get_jira_ticket", "start_jira_ticket", "submit_jira_ticket_for_review"]
    assert sub["skills"] == ["/agents/coder/skills/"]
    assert sub["permissions"] == registry.permissions_for(registry.get_agent("coder"))


async def test_graph_reads_all_agent_folders(graph, monkeypatch):
    run(manage.create_agent, name="poet", description="Writes poems", system_prompt="You are a poet.")
    captured = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        agent = Mock()

        async def ainvoke(inp):
            return {"messages": inp["messages"] + [AIMessage(content="hi")]}

        agent.ainvoke = ainvoke
        return agent

    # agent/__init__ re-exports `graph`, so patch the module object directly
    monkeypatch.setattr(sys.modules["agent.graph"], "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(registry, "load_model", lambda name: Mock(name=name))
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello")]},
        config={"configurable": {"thread_id": "t"}},
    )
    assert result["messages"][-1].content == "hi"
    assert {s["name"] for s in captured["subagents"]} == {"admin", "coder", "poet", "researcher", "slack"}
    assert captured["skills"] == ["/agents/default/skills/"]
    assert manage.create_agent in captured["tools"]


class FakeJira:
    def __init__(self, users):
        self.users, self.calls = users, []

    def user_find_by_user_string(self, query):
        return self.users

    def get_issue_transitions(self, key):
        return [{"to": "In Progress"}, {"to": "In Review"}, {"to": "Done"}]

    def set_issue_status(self, key, status):
        self.calls.append(("status", key, status))

    def issue_add_comment(self, key, body):
        self.calls.append(("comment", key, body))

    def assign_issue(self, key, account_id):
        self.calls.append(("assign", key, account_id))


def patch_jira(monkeypatch, fake):
    import langchain_community.utilities.jira as jira_mod

    monkeypatch.setattr(jira_mod, "JiraAPIWrapper", lambda: Mock(jira=fake))


def test_submit_for_review_moves_comments_assigns(monkeypatch):
    from agent.core.catalog import submit_jira_ticket_for_review

    fake = FakeJira([{"displayName": "dmitri", "accountId": "acc-1", "accountType": "atlassian"}])
    patch_jira(monkeypatch, fake)
    out = submit_jira_ticket_for_review.invoke({"issue_key": "PP-3", "comment": "Done, see /workspace/pp-3", "reviewer": "dmitri"})
    assert "assigned to dmitri" in out
    assert fake.calls == [
        ("status", "PP-3", "In Review"),
        ("comment", "PP-3", "[~accountid:acc-1] Done, see /workspace/pp-3"),
        ("assign", "PP-3", "acc-1"),
    ]


def test_submit_for_review_ambiguous_user(monkeypatch):
    from agent.core.catalog import submit_jira_ticket_for_review

    fake = FakeJira([
        {"displayName": "dmitri a", "accountId": "1", "accountType": "atlassian"},
        {"displayName": "dmitri b", "accountId": "2", "accountType": "atlassian"},
    ])
    patch_jira(monkeypatch, fake)
    out = submit_jira_ticket_for_review.invoke({"issue_key": "PP-3", "comment": "x", "reviewer": "dmitri"})
    assert out.startswith("Error") and fake.calls == []
