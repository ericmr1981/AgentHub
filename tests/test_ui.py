from __future__ import annotations

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


from fastapi.testclient import TestClient

from agenthub.ui import create_app


def test_ui_dashboard_api_and_page(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    task = service.create_task("UI", "Render page", "normal", [])
    service.push_event(task["id"], "codex", "status", "render me", [])

    client = TestClient(create_app(paths))

    api_response = client.get("/api/dashboard")
    page_response = client.get("/")

    assert api_response.status_code == 200
    assert api_response.json()["tasks"][0]["title"] == "UI"
    assert page_response.status_code == 200
    assert "AgentHub Radar" in page_response.text
    assert "render me" in page_response.text


def test_dashboard_snapshot_contains_radar_tasks_and_timeline(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.register_agent("claude-code", "claude-code")
    service.heartbeat_agent("codex", "active")
    task = service.create_task("Dashboard", "Show status", "normal", [])
    service.claim_task(task["id"], "codex")
    service.push_event(task["id"], "codex", "status", "visible", [])

    snapshot = service.dashboard_snapshot()

    assert snapshot["radar"]["agents_total"] == 2
    assert snapshot["radar"]["agents_active"] == 1
    assert snapshot["radar"]["tasks_blocked"] == 0
    assert snapshot["tasks"][0]["id"] == "T000001"
    assert snapshot["timeline"][-1]["body"] == "visible"
