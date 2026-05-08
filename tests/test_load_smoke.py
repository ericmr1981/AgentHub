from __future__ import annotations

import time

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


def test_insert_1000_short_events_and_query_timeline(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.register_agent("claude-code", "claude-code")
    task = service.create_task("Load", "Smoke test events", "normal", [])

    start = time.monotonic()
    for index in range(1000):
        service.push_event(task["id"], "codex", "status", f"event {index}", [])
    snapshot = service.dashboard_snapshot()
    elapsed = time.monotonic() - start

    assert len(snapshot["timeline"]) == 100
    assert snapshot["timeline"][-1]["body"] == "event 999"
    assert elapsed < 10
