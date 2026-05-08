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


def test_push_event_and_pull_inbox_advances_cursor(service):
    task = service.create_task("Events", "Test inbox", "normal", [])
    event = service.push_event(task["id"], "codex", "status", "schema done", [])

    first_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=False)
    second_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=False)

    assert event["id"] == "E000001"
    assert first_pull["events"][0]["body"] == "schema done"
    assert first_pull["last_cursor"] == 1
    assert second_pull["events"] == []


def test_pull_inbox_peek_does_not_advance_cursor(service):
    task = service.create_task("Peek", "Test peek", "normal", [])
    service.push_event(task["id"], "codex", "status", "peekable", [])

    first_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=True)
    second_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=False)

    assert first_pull["events"][0]["body"] == "peekable"
    assert second_pull["events"][0]["body"] == "peekable"


def test_event_body_budget_is_enforced(service):
    task = service.create_task("Budget", "Test body budget", "normal", [])
    long_body = "x" * 281

    with pytest.raises(HubError) as exc:
        service.push_event(task["id"], "codex", "status", long_body, [])

    assert exc.value.code == "BODY_TOO_LARGE"


def test_block_task_creates_blocked_event(service):
    task = service.create_task("Block", "Test block", "normal", [])
    service.claim_task(task["id"], "codex")
    blocked = service.block_task(task["id"], "codex", "needs schema")

    assert blocked["status"] == "blocked"
    assert blocked["summary"] == "needs schema"

    shown = service.show_task(task["id"], brief=True)
    assert shown["recent_events"][-1]["type"] == "blocked"


def test_close_task_marks_done_and_sets_summary(service):
    task = service.create_task("Close", "Test close", "normal", [])
    service.claim_task(task["id"], "codex")
    closed = service.close_task(task["id"], "codex", "implemented CLI")

    assert closed["status"] == "done"
    assert closed["summary"] == "implemented CLI"
    assert closed["closed_at"] is not None


def test_reassign_task_changes_owner(service):
    task = service.create_task("Reassign", "Test reassign", "normal", [])
    service.claim_task(task["id"], "codex")
    reassigned = service.reassign_task(task["id"], "claude-code")

    assert reassigned["owner_agent_id"] == "claude-code"
    assert reassigned["status"] == "claimed"
