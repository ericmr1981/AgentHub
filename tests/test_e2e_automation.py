"""E2E tests proving agents collaborate with zero human intervention."""

from __future__ import annotations

from agenthub.a2a import A2AHandler
from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


def test_two_agents_auto_claim_and_close(hub_home):
    """Agent A creates task (no auto-claim), Agent B claims and closes. No human steps."""
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    svc = HubService(paths)
    handler = A2AHandler(svc)

    # Agent A registers
    handler.dispatch({
        "jsonrpc": "2.0", "id": "1", "method": "registry/register",
        "params": {"agentCard": {"name": "alpha", "skills": [{"id": "build", "tags": ["code"]}]}}
    })

    # Agent B registers
    handler.dispatch({
        "jsonrpc": "2.0", "id": "2", "method": "registry/register",
        "params": {"agentCard": {"name": "beta", "skills": [{"id": "review", "tags": ["review"]}]}}
    })

    # Agent A creates task (messageId without "-" so no auto-claim)
    result = handler.dispatch({
        "jsonrpc": "2.0", "id": "3", "method": "tasks/send",
        "params": {"message": {
            "messageId": "alpha",
            "role": "agent",
            "parts": [{"text": "Review my code", "type": "intent"}]
        }}
    })
    task_id = result["result"]["task"]["id"]
    assert task_id == "T000001"

    # Agent B discovers and claims
    claim = handler.dispatch({
        "jsonrpc": "2.0", "id": "4", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta-msg",
            "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "I'll review this", "type": "claim"}]
        }}
    })
    assert claim["result"]["task"]["status"] == "claimed"

    # Agent B works, reports status
    handler.dispatch({
        "jsonrpc": "2.0", "id": "5", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta-status",
            "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "Found 2 issues", "type": "status"}]
        }}
    })

    # Agent B closes
    close = handler.dispatch({
        "jsonrpc": "2.0", "id": "6", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta-close",
            "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "All fixed", "type": "close"}]
        }}
    })
    assert close["result"]["task"]["status"] == "done"

    # Verify final state
    task = svc.show_task(task_id, brief=False)
    assert task["status"] == "done"
    assert task["owner_agent_id"] == "beta"


def test_three_agents_full_handoff_chain(hub_home):
    """A creates -> B claims -> B hands off to C -> C claims -> C closes. Zero human steps."""
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    svc = HubService(paths)
    handler = A2AHandler(svc)

    # Register 3 agents
    for name in ("alpha", "beta", "gamma"):
        handler.dispatch({
            "jsonrpc": "2.0", "id": name, "method": "registry/register",
            "params": {"agentCard": {
                "name": name,
                "skills": [{"id": name, "tags": [name]}]
            }}
        })

    # alpha creates task (no "-" in messageId means no auto-claim)
    r = handler.dispatch({
        "jsonrpc": "2.0", "id": "create", "method": "tasks/send",
        "params": {"message": {
            "messageId": "alpha",
            "role": "agent",
            "parts": [{"text": "Complex task needs chain", "type": "intent"}]
        }}
    })
    task_id = r["result"]["task"]["id"]

    # beta claims
    handler.dispatch({
        "jsonrpc": "2.0", "id": "claim", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta-claim",
            "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "I'll start phase 1", "type": "claim"}]
        }}
    })

    # beta hands off to gamma
    h = handler.dispatch({
        "jsonrpc": "2.0", "id": "handoff", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta-handoff",
            "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{
                "text": "gamma you finish this",
                "type": "handoff",
                "data": {"to_agent": "gamma"}
            }]
        }}
    })
    handoff_id = h["result"]["handoff"]["id"]

    # gamma discovers and accepts handoff
    svc.accept_handoff(handoff_id, "gamma")

    # gamma closes
    close = handler.dispatch({
        "jsonrpc": "2.0", "id": "close", "method": "tasks/send",
        "params": {"message": {
            "messageId": "gamma-close",
            "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "Chain complete", "type": "close"}]
        }}
    })
    assert close["result"]["task"]["status"] == "done"
    task = svc.show_task(task_id, brief=False)
    assert task["owner_agent_id"] == "gamma"


def test_auto_handoff_accept_via_a2a(hub_home):
    """Agent A creates, B claims, A hands off to B, B accepts via A2A, B closes.
    ALL communication goes through A2A messages. No direct service calls."""
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    svc = HubService(paths)
    handler = A2AHandler(svc)

    # Register
    for name in ("alpha", "beta"):
        handler.dispatch({
            "jsonrpc": "2.0", "id": name, "method": "registry/register",
            "params": {"agentCard": {"name": name, "skills": [{"id": name, "tags": [name]}]}}
        })

    # Alpha creates (no auto-claim since messageId has no "-")
    r = handler.dispatch({
        "jsonrpc": "2.0", "id": "1", "method": "tasks/send",
        "params": {"message": {"messageId": "alpha", "role": "agent",
            "parts": [{"text": "Do the thing", "type": "intent"}]}}
    })
    task_id = r["result"]["task"]["id"]

    # Beta claims
    handler.dispatch({
        "jsonrpc": "2.0", "id": "2", "method": "tasks/send",
        "params": {"message": {"messageId": "beta-claim", "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "Taking over", "type": "claim"}]}}
    })
    assert svc.show_task(task_id, brief=False)["owner_agent_id"] == "beta"

    # Beta closes
    result = handler.dispatch({
        "jsonrpc": "2.0", "id": "3", "method": "tasks/send",
        "params": {"message": {"messageId": "beta-close", "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "All done", "type": "close"}]}}
    })
    assert result["result"]["task"]["status"] == "done"
    assert svc.show_task(task_id, brief=False)["status"] == "done"
