from __future__ import annotations

import pytest

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.errors import HubError
from agenthub.service import HubService


@pytest.fixture()
def service(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    hub = HubService(paths)
    hub.register_agent("codex", "codex")
    hub.register_agent("claude-code", "claude-code")
    return hub


def test_create_list_show_and_claim_task(service):
    task = service.create_task("Wire CLI", "Build CLI path", "normal", [])
    listed = service.list_tasks(status="open")
    claimed = service.claim_task(task["id"], "codex")
    shown = service.show_task(task["id"], brief=True)

    assert task["id"] == "T000001"
    assert listed[0]["title"] == "Wire CLI"
    assert claimed["status"] == "claimed"
    assert claimed["owner_agent_id"] == "codex"
    assert shown["recent_events"][-1]["type"] == "claim"


def test_claim_task_is_atomic(service):
    task = service.create_task("Race", "Only one owner", "normal", [])
    service.claim_task(task["id"], "codex")

    with pytest.raises(HubError) as exc:
        service.claim_task(task["id"], "claude-code")

    assert exc.value.code == "TASK_ALREADY_CLAIMED"
