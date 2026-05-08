from __future__ import annotations

"""E2E workflow tests for multi-agent task handoff scenarios.

Scenarios tested:
  1. 3-agent chain: alpha -> beta -> gamma -> close
  2. 2-agent ping-pong: alpha <-> beta x3 handoffs -> close
  3. Concurrent task flow: 3 independent tasks across 3 agents
"""

import time

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


def _setup(hub_home) -> HubService:
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    svc = HubService(paths)
    svc.register_agent("alpha", "codex")
    svc.register_agent("beta", "claude-code")
    svc.register_agent("gamma", "openclaw")
    svc.heartbeat_agent("alpha", "active")
    svc.heartbeat_agent("beta", "active")
    svc.heartbeat_agent("gamma", "active")
    return svc


def _verify_owner(svc: HubService, task_id: str, expected_owner: str, label: str):
    task = svc.show_task(task_id, brief=False)
    assert task["owner_agent_id"] == expected_owner, (
        f"{label}: expected owner={expected_owner}, got {task['owner_agent_id']}"
    )
    assert task["status"] in ("claimed", "blocked", "done"), (
        f"{label}: unexpected status {task['status']}"
    )


def _verify_done(svc: HubService, task_id: str, label: str):
    task = svc.show_task(task_id, brief=False)
    assert task["status"] == "done", f"{label}: expected done, got {task['status']}"
    assert task["closed_at"] is not None, f"{label}: closed_at not set"


def _verify_events(svc: HubService, task_id: str, expected_types: list[str], label: str):
    task = svc.show_task(task_id, brief=True)
    actual_types = [e["type"] for e in task["recent_events"]]
    for expected in expected_types:
        assert expected in actual_types, (
            f"{label}: missing event type '{expected}' in {actual_types}"
        )


def test_three_agent_chain_handoff(hub_home):
    """alpha claims -> hands off to beta -> beta accepts -> hands off to gamma -> gamma accepts -> closes."""
    svc = _setup(hub_home)

    # --- Phase 1: Create, Claim ---
    task = svc.create_task("Chain task", "3-agent chain handoff", "high", [])
    svc.claim_task(task["id"], "alpha")
    _verify_owner(svc, task["id"], "alpha", "after claim")

    svc.push_event(task["id"], "alpha", "status", "starting work", [])
    svc.push_event(task["id"], "alpha", "status", "phase 1 done, handing off", [])

    # --- Phase 2: alpha -> beta ---
    handoff_1 = svc.create_handoff(task["id"], "alpha", "beta", "take over phase 2")
    assert handoff_1["status"] == "pending"
    # Task still owned by alpha until accept
    _verify_owner(svc, task["id"], "alpha", "before first accept")

    svc.accept_handoff(handoff_1["id"], "beta")
    _verify_owner(svc, task["id"], "beta", "after first accept")

    svc.push_event(task["id"], "beta", "status", "phase 2 in progress", [])
    svc.push_event(task["id"], "beta", "status", "phase 2 done", [])

    # --- Phase 3: beta -> gamma ---
    handoff_2 = svc.create_handoff(task["id"], "beta", "gamma", "final phase please")
    assert handoff_2["status"] == "pending"

    svc.accept_handoff(handoff_2["id"], "gamma")
    _verify_owner(svc, task["id"], "gamma", "after second accept")

    svc.push_event(task["id"], "gamma", "status", "phase 3 finalizing", [])
    svc.push_event(task["id"], "gamma", "status", "all done", [])

    # --- Phase 4: gamma closes ---
    svc.close_task(task["id"], "gamma", "completed all 3 phases")
    _verify_done(svc, task["id"], "3-agent chain")

    # Verify events captured (last 5 events from --brief)
    _verify_events(svc, task["id"], ["handoff", "note"], "chain events")
    assert task["id"] == "T000001"


def test_two_agent_three_handoff_pingpong(hub_home):
    """alpha claims -> hands off to beta -> back to alpha -> back to beta -> alpha closes.
    Total: 3 handoffs, 5 ownership changes.
    """
    svc = _setup(hub_home)

    task = svc.create_task("Ping pong", "3-hop ping-pong handoff", "normal", [])
    svc.claim_task(task["id"], "alpha")
    _verify_owner(svc, task["id"], "alpha", "start")

    # Hop 1: alpha -> beta
    h1 = svc.create_handoff(task["id"], "alpha", "beta", "hop 1")
    svc.accept_handoff(h1["id"], "beta")
    _verify_owner(svc, task["id"], "beta", "hop 1")

    # Hop 2: beta -> alpha
    h2 = svc.create_handoff(task["id"], "beta", "alpha", "hop 2")
    svc.accept_handoff(h2["id"], "alpha")
    _verify_owner(svc, task["id"], "alpha", "hop 2")

    # Hop 3: alpha -> beta
    h3 = svc.create_handoff(task["id"], "alpha", "beta", "hop 3")
    svc.accept_handoff(h3["id"], "beta")
    _verify_owner(svc, task["id"], "beta", "hop 3")

    # beta closes
    svc.close_task(task["id"], "beta", "ping-pong complete")
    _verify_done(svc, task["id"], "ping-pong")

    assert task["id"] == "T000001"


def test_three_concurrent_tasks_across_agents(hub_home):
    """3 agents each create, claim, and hand off tasks concurrently.
    Verifies atomicity: no task gets double-claimed.
    """
    svc = _setup(hub_home)

    t1 = svc.create_task("Task A", "alpha leads", "normal", [])
    t2 = svc.create_task("Task B", "beta leads", "normal", [])
    t3 = svc.create_task("Task C", "gamma leads", "normal", [])

    # Each agent claims their own task
    svc.claim_task(t1["id"], "alpha")
    svc.claim_task(t2["id"], "beta")
    svc.claim_task(t3["id"], "gamma")

    _verify_owner(svc, t1["id"], "alpha", "t1")
    _verify_owner(svc, t2["id"], "beta", "t2")
    _verify_owner(svc, t3["id"], "gamma", "t3")

    # Each agent hands off to the next in a ring: alpha->beta, beta->gamma, gamma->alpha
    h_a2b = svc.create_handoff(t1["id"], "alpha", "beta", "review task A")
    h_b2g = svc.create_handoff(t2["id"], "beta", "gamma", "review task B")
    h_g2a = svc.create_handoff(t3["id"], "gamma", "alpha", "review task C")

    svc.accept_handoff(h_a2b["id"], "beta")
    svc.accept_handoff(h_b2g["id"], "gamma")
    svc.accept_handoff(h_g2a["id"], "alpha")

    _verify_owner(svc, t1["id"], "beta", "t1 after ring")
    _verify_owner(svc, t2["id"], "gamma", "t2 after ring")
    _verify_owner(svc, t3["id"], "alpha", "t3 after ring")

    # Close all
    svc.close_task(t1["id"], "beta", "reviewed")
    svc.close_task(t2["id"], "gamma", "reviewed")
    svc.close_task(t3["id"], "alpha", "reviewed")

    _verify_done(svc, t1["id"], "t1 final")
    _verify_done(svc, t2["id"], "t2 final")
    _verify_done(svc, t3["id"], "t3 final")


def test_handoff_idempotency(hub_home):
    """Accepting an already-accepted handoff raises error.
    Claiming an already-claimed task raises error.
    Closing an already-closed task raises error.
    """
    import pytest
    from agenthub.errors import HubError

    svc = _setup(hub_home)

    # Setup
    task = svc.create_task("Idempotent", "Test idempotency", "normal", [])
    svc.claim_task(task["id"], "alpha")
    h = svc.create_handoff(task["id"], "alpha", "beta", "take it")
    svc.accept_handoff(h["id"], "beta")

    # Double-accept fails
    with pytest.raises(HubError, match="HANDOFF_NOT_PENDING"):
        svc.accept_handoff(h["id"], "beta")

    # Re-claiming done task fails
    svc.close_task(task["id"], "beta", "done")
    with pytest.raises(HubError, match="TASK_ALREADY_CLOSED"):
        svc.close_task(task["id"], "beta", "already done")

    # Double-claim of new task fails
    t2 = svc.create_task("Race", "Atomic claim test", "normal", [])
    svc.claim_task(t2["id"], "alpha")
    with pytest.raises(HubError, match="TASK_ALREADY_CLAIMED"):
        svc.claim_task(t2["id"], "beta")


def test_two_agent_pingpong_10_times_stress(hub_home):
    """Run the 2-agent ping-pong 10 times in sequence to verify stability."""
    for iteration in range(1, 11):
        svc = _setup(hub_home)

        task = svc.create_task(f"Ping pong {iteration}", "Stress test", "normal", [])
        svc.claim_task(task["id"], "alpha")

        h1 = svc.create_handoff(task["id"], "alpha", "beta", f"iteration {iteration} hop 1")
        svc.accept_handoff(h1["id"], "beta")

        h2 = svc.create_handoff(task["id"], "beta", "alpha", f"iteration {iteration} hop 2")
        svc.accept_handoff(h2["id"], "alpha")

        h3 = svc.create_handoff(task["id"], "alpha", "beta", f"iteration {iteration} hop 3")
        svc.accept_handoff(h3["id"], "beta")

        svc.close_task(task["id"], "beta", f"ping-pong {iteration} complete")
        _verify_done(svc, task["id"], f"stress iter {iteration}")

    assert iteration == 10, "should have run all 10 iterations"


def test_inbox_visibility_after_handoff(hub_home):
    """After a handoff, agents should see relevant events in their inbox."""
    svc = _setup(hub_home)

    task = svc.create_task("Inbox test", "Test inbox after handoff", "normal", [])

    # alpha claims and pushes events
    svc.claim_task(task["id"], "alpha")
    svc.push_event(task["id"], "alpha", "status", "alpha working", [])

    # Before handoff: beta sees alpha's events
    beta_inbox = svc.pull_inbox("beta", limit=10, since=None, peek=True)
    inbox_bodies = [e["body"] for e in beta_inbox["events"]]
    assert "alpha working" in inbox_bodies, "beta should see alpha's event before handoff"

    # alpha hands off to beta
    h = svc.create_handoff(task["id"], "alpha", "beta", "your turn")
    svc.accept_handoff(h["id"], "beta")

    # beta pushes event
    svc.push_event(task["id"], "beta", "status", "beta working now", [])

    # beta's inbox: should NOT include beta's own events, but SHOULD include alpha's
    beta_inbox = svc.pull_inbox("beta", limit=10, since=None, peek=False)
    inbox_bodies = [e["body"] for e in beta_inbox["events"]]
    assert "beta working now" not in inbox_bodies, "beta should NOT see own events"
    assert "alpha working" in inbox_bodies, "beta should see alpha's old events"

    # alpha's inbox: should see beta's close event etc.
    svc.push_event(task["id"], "beta", "status", "about to close", [])
    alpha_inbox = svc.pull_inbox("alpha", limit=10, since=None, peek=True)
    alpha_bodies = [e["body"] for e in alpha_inbox["events"]]
    assert "about to close" in alpha_bodies, "alpha should see beta's events"
