from __future__ import annotations

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


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
