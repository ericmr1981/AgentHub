from __future__ import annotations

from fastapi.testclient import TestClient

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService
from agenthub.registry import AgentRegistry
from agenthub.ui import create_app


def test_a2a_tasks_send_creates_task(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    svc = HubService(paths)
    reg = AgentRegistry(svc)
    reg.register("alpha", {"name": "alpha", "skills": [{"id": "a", "tags": ["code"]}]})
    reg.register("beta", {"name": "beta", "skills": [{"id": "b", "tags": ["review"]}]})

    client = TestClient(create_app(paths))

    resp = client.post("/a2a", json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/send",
        "params": {
            "message": {
                "messageId": "alpha-1",
                "role": "agent",
                "parts": [
                    {"text": "Review my PR for security issues", "type": "intent"}
                ]
            }
        }
    })

    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["task"]["id"] == "T000001"
    assert result["task"]["status"] == "claimed"


def test_a2a_tasks_list(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    svc = HubService(paths)
    svc.register_agent("alpha", "codex")
    svc.create_task("Task 1", "intent 1", "normal", [])

    client = TestClient(create_app(paths))
    resp = client.post("/a2a", json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/list",
        "params": {}
    })

    assert resp.status_code == 200
    tasks = resp.json()["result"]["tasks"]
    assert len(tasks) >= 1
