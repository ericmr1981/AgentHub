from __future__ import annotations

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService
from agenthub.registry import AgentRegistry


def test_register_agent_with_card(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    registry = AgentRegistry(HubService(paths))

    card = {
        "name": "code-reviewer",
        "description": "Reviews Python code",
        "skills": [
            {"id": "review", "tags": ["python", "code-review"]},
            {"id": "fix", "tags": ["python", "debugging"]},
        ],
        "url": "http://localhost:9001/a2a",
    }
    registry.register("code-reviewer", card)
    agent = registry.lookup("code-reviewer")

    assert agent["name"] == "code-reviewer"
    assert agent["skills"][0]["tags"] == ["python", "code-review"]


def test_list_agents_returns_all_cards(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    registry = AgentRegistry(HubService(paths))

    registry.register("alpha", {"name": "alpha", "skills": [{"id": "a", "tags": ["ml"]}]})
    registry.register("beta", {"name": "beta", "skills": [{"id": "b", "tags": ["web"]}]})

    agents = registry.list_all()
    assert len(agents) >= 2
