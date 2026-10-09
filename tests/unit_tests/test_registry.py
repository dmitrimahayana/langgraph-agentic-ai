"""Unit tests for the agent/skill registry and management tools."""

import sys
from unittest.mock import Mock

import pytest
from deepagents.middleware.skills import _alist_skills
from langchain_core.messages import AIMessage, HumanMessage

from agent import registry
from agent.tools import manage

pytestmark = pytest.mark.anyio


def tool_runtime(store):
    rt = Mock()
    rt.store = store
    return rt


async def call(tool, store, **kwargs):
    return await tool.coroutine(runtime=tool_runtime(store), **kwargs)


async def test_seed_creates_default_team(store):
    await registry.aseed(store)
    names = [s.name for s in await registry.aget_agents(store)]
    assert names == ["admin", "coder", "researcher"]
    assert set(await registry.alist_skills(store)) == {"jira-workflow", "web-research"}


async def test_seed_runs_once(store):
    await registry.aseed(store)
    await registry.adelete_agent(store, "coder")
    await registry.aseed(store)
    assert "coder" not in [s.name for s in await registry.aget_agents(store)]


async def test_create_agent_with_tools_and_skills(store):
    await call(manage.save_skill, store, name="release-notes", description="Write release notes", instructions="# Steps\n1. Do it")
    out = await call(
        manage.create_agent, store,
        name="pm", description="Project manager", system_prompt="You are PM.",
        tools=["jira"], skills=["release-notes"],
    )
    assert "created" in out
    spec = await registry.aget_agent(store, "pm")
    assert spec.tools == ["jira"]
    assert spec.skills == ["release-notes"]

    # SkillsMiddleware reads the agent's skill folder through the composite backend
    skills = await _alist_skills(registry.make_backend(store), "/agents/pm/skills/")
    assert [s["name"] for s in skills] == ["release-notes"]


async def test_create_agent_rejects_unknown_tool_and_skill(store):
    out = await call(manage.create_agent, store, name="x", description="d", system_prompt="p", tools=["rm_rf"])
    assert out.startswith("Error") and "rm_rf" in out
    out = await call(manage.create_agent, store, name="x", description="d", system_prompt="p", skills=["nope"])
    assert out.startswith("Error") and "nope" in out
    assert await registry.aget_agent(store, "x") is None


async def test_create_agent_rejects_bad_and_reserved_names(store):
    assert (await call(manage.create_agent, store, name="Bad Name", description="d", system_prompt="p")).startswith("Error")
    assert (await call(manage.create_agent, store, name="general-purpose", description="d", system_prompt="p")).startswith("Error")


async def test_update_skill_resyncs_agents(store):
    await call(manage.save_skill, store, name="s1", description="v1", instructions="old")
    await call(manage.create_agent, store, name="a", description="d", system_prompt="p", skills=["s1"])
    out = await call(manage.save_skill, store, name="s1", description="v2", instructions="new body")
    assert "a" in out
    copy = await registry.agent_files_backend(store).aread("/a/skills/s1/SKILL.md")
    assert "new body" in copy.file_data["content"]


async def test_update_agent_unassigns_skill(store):
    await call(manage.save_skill, store, name="s1", description="d", instructions="x")
    await call(manage.create_agent, store, name="a", description="d", system_prompt="p", skills=["s1"])
    await call(manage.update_agent, store, name="a", skills=[], tools=["web_search"])
    spec = await registry.aget_agent(store, "a")
    assert spec.skills == [] and spec.tools == ["web_search"]
    assert await _alist_skills(registry.make_backend(store), "/agents/a/skills/") == []


async def test_delete_agent(store):
    await call(manage.create_agent, store, name="a", description="d", system_prompt="p")
    assert "deleted" in await call(manage.delete_agent, store, name="a")
    assert (await call(manage.delete_agent, store, name="a")).startswith("Error")


def test_build_subagents_shape():
    spec = registry.AgentSpec(name="pm", description="d", system_prompt="p", tools=["save_script_file"])
    (sub,) = registry.build_subagents([spec])
    assert sub["name"] == "pm"
    assert [t.name for t in sub["tools"]] == ["save_script_file"]
    assert sub["skills"] == ["/agents/pm/skills/"]


async def test_graph_builds_deep_agent_with_subagents(graph, monkeypatch):
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
    assert {s["name"] for s in captured["subagents"]} == {"admin", "coder", "researcher"}
    assert manage.create_agent in captured["tools"]
