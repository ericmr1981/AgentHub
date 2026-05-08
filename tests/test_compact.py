from __future__ import annotations

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


def test_compact_summarizes_old_events(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.register_agent("claude-code", "claude-code")
    task = service.create_task("Compact", "Test compact", "normal", [])

    for i in range(10):
        service.push_event(task["id"], "codex", "status", f"event {i}", [])

    result = service.compact_events(days=0, mode="summarize")

    assert result["events_compacted"] == 10
    assert result["summary"] is not None
    assert result["mode"] == "summarize"
