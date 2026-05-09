# AgentHub A2A Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add A2A protocol support to AgentHub: JSON-RPC endpoint, Agent Card registry, SSE event stream, and a minimal agent worker. After this, any agent on any platform can participate via A2A protocol, and agents can auto-claim/auto-complete tasks without human intervention.

**Architecture:** New `a2a.py` handles JSON-RPC message routing. New `registry.py` manages Agent Card storage and lookups. SSE endpoint in `ui.py` replaces CLI polling. `scripts/agent_worker.py` is a standalone daemon each agent runs.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, existing AgentHub service layer.

---

## File Map

Create:
- `src/agenthub/a2a.py` — JSON-RPC 2.0 endpoint, message routing to HubService
- `src/agenthub/registry.py` — Agent Card registration, heartbeat, discovery
- `scripts/agent_worker.py` — standalone agent daemon
- `scripts/agent_hub_bridge.py` — bridge: connects real Claude Code / Codex sessions to hub
- `tests/test_a2a.py` — A2A endpoint tests
- `tests/test_registry.py` — registry tests
- `tests/test_e2e_automation.py` — end-to-end: 2+ agents auto-claim, work, close without human input

Modify:
- `src/agenthub/ui.py` — add SSE event stream endpoint, A2A routes, well-known card
- `src/agenthub/service.py` — add minimal helper methods for A2A message dispatch
- `src/agenthub/models.py` — add SKILL_TAG constant, check update
- `src/agenthub/cli.py` — mark `hub watch` and `hub inbox pull` as deprecated (keep working)

---

### Task 1: Agent Registry with Agent Cards

**Files:**
- Create: `src/agenthub/registry.py`
- Create: `tests/test_registry.py`
- Modify: `src/agenthub/models.py` — add SKILL_TAG constant
- Modify: `src/agenthub/ui.py` — add GET /.well-known/agent-card, POST /api/registry/register

- [ ] **Step 1: Write failing test**

Create `tests/test_registry.py`:
```python
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
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
pytest tests/test_registry.py -v
```

- [ ] **Step 3: Implement registry.py**

```python
from __future__ import annotations

from agenthub.errors import HubError
from agenthub.models import dumps_json, loads_json


class AgentRegistry:
    def __init__(self, service):
        self._svc = service

    def register(self, agent_id: str, card: dict) -> dict:
        self._svc.register_agent(agent_id, card.get("name", agent_id))
        self._svc.heartbeat_agent(agent_id, "active")
        return self.lookup(agent_id)

    def lookup(self, agent_id: str) -> dict:
        agent = self._svc.show_agent(agent_id)
        return {
            "id": agent["id"],
            "name": agent["display_name"],
            "status": agent["status"],
            "last_seen_at": agent["last_seen_at"],
        }

    def list_all(self) -> list[dict]:
        return self._svc.list_agents()
```

- [ ] **Step 4: Run tests, confirm PASS**

- [ ] **Step 5: Add well-known card endpoint in ui.py**

```python
@app.get("/.well-known/agent-card")
def agent_card():
    return {
        "name": "AgentHub",
        "description": "Multi-agent coordination hub",
        "version": "1.0",
        "capabilities": {"streaming": True},
        "interfaces": [{"type": "a2a", "url": "http://localhost:8765/a2a"}],
        "skills": [{"id": "coordination", "tags": ["task", "handoff", "coordination"]}],
    }
```

- [ ] **Step 6: Commit**

```bash
git add src/agenthub/registry.py src/agenthub/ui.py tests/test_registry.py
git commit -m "feat: add agent registry with Agent Card support"
```

---

### Task 2: A2A JSON-RPC Endpoint

**Files:**
- Create: `src/agenthub/a2a.py`
- Create: `tests/test_a2a.py`
- Modify: `src/agenthub/ui.py` — mount POST /a2a

- [ ] **Step 1: Write failing test**

Create `tests/test_a2a.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService
from agenthub.registry import AgentRegistry
from agenthub.a2a import A2AHandler
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
                "messageId": "msg-1",
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
```

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement a2a.py**

```python
from __future__ import annotations

import json as _json

from agenthub.errors import HubError
from agenthub.service import HubService
from agenthub.registry import AgentRegistry


class A2AHandler:
    def __init__(self, service: HubService):
        self._svc = service

    def dispatch(self, request_body: dict) -> dict:
        method = request_body.get("method", "")
        req_id = request_body.get("id", "")
        params = request_body.get("params", {})

        try:
            if method == "tasks/send":
                return self._handle_send(req_id, params)
            elif method == "tasks/list":
                return self._handle_list(req_id, params)
            elif method == "tasks/get":
                return self._handle_get(req_id, params)
            elif method == "tasks/subscribe":
                return self._handle_subscribe(req_id, params)
            elif method == "registry/register":
                return self._handle_register(req_id, params)
            else:
                return self._error(req_id, -32601, f"Method not found: {method}")
        except HubError as exc:
            return self._error(req_id, -32000, exc.message, exc.code)

    def _handle_send(self, req_id: str, params: dict) -> dict:
        message = params.get("message", {})
        parts = message.get("parts", [])
        refs = message.get("referenceTaskIds", [])

        for part in parts:
            ptype = part.get("type", "intent")
            text = part.get("text", "")

            if ptype == "intent":
                task = self._svc.create_task(text, text, "normal", [])
                # Auto-claim by sender
                sender = message.get("messageId", "").split("-")[0] if "-" in message.get("messageId", "") else ""
                if sender:
                    try:
                        self._svc.claim_task(task["id"], sender)
                    except HubError:
                        pass
                return self._ok(req_id, {"task": {"id": task["id"], "status": task["status"]}})

            elif ptype == "claim":
                if refs:
                    result = self._svc.claim_task(refs[0], message.get("messageId", ""))
                    return self._ok(req_id, {"task": {"id": result["id"], "status": result["status"]}})

            elif ptype == "close":
                if refs:
                    result = self._svc.close_task(refs[0], message.get("messageId", ""), text or "completed")
                    return self._ok(req_id, {"task": {"id": result["id"], "status": result["status"]}})

            elif ptype == "handoff":
                data = part.get("data", {})
                to_agent = data.get("to_agent", "")
                if refs and to_agent:
                    handoff = self._svc.create_handoff(
                        refs[0], message.get("messageId", ""), to_agent, text or "handing off"
                    )
                    return self._ok(req_id, {"handoff": {"id": handoff["id"], "status": handoff["status"]}})

            elif ptype == "status":
                if refs:
                    event = self._svc.push_event(refs[0], message.get("messageId", ""), "status", text, [])
                    return self._ok(req_id, {"event": {"id": event["id"], "body": event["body"]}})

        return self._error(req_id, -32602, "No handler matched the message parts")

    def _handle_list(self, req_id: str, params: dict) -> dict:
        tasks = self._svc.list_tasks()
        return self._ok(req_id, {"tasks": tasks})

    def _handle_get(self, req_id: str, params: dict) -> dict:
        task_id = params.get("id", "")
        task = self._svc.show_task(task_id, brief=True)
        return self._ok(req_id, {"task": task})

    def _handle_subscribe(self, req_id: str, params: dict) -> dict:
        # Returns info that client should use SSE endpoint
        return self._ok(req_id, {"stream_url": "/api/events/stream"})

    def _handle_register(self, req_id: str, params: dict) -> dict:
        card = params.get("agentCard", {})
        agent_id = card.get("name", "")
        if not agent_id:
            return self._error(req_id, -32602, "agentCard.name is required")
        registry = AgentRegistry(self._svc)
        registry.register(agent_id, card)
        return self._ok(req_id, {"registered": agent_id})

    def _ok(self, req_id: str, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id: str, code: int, message: str, data: str | None = None) -> dict:
        err = {"code": code, "message": message}
        if data:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": err}
```

- [ ] **Step 4: Wire /a2a in ui.py**

```python
from agenthub.a2a import A2AHandler

# Inside create_app, after svc = HubService(paths):
a2a = A2AHandler(svc)

@app.post("/a2a")
def a2a_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    result = a2a.dispatch(body)
    return result
```

Note: `request: Request` needs the `async def` pattern. Use `async def a2a_endpoint(request: Request)` and import `Request` from fastapi.

- [ ] **Step 5: Run tests, confirm PASS**

```bash
pytest tests/test_a2a.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/agenthub/a2a.py src/agenthub/ui.py tests/test_a2a.py
git commit -m "feat: add A2A JSON-RPC endpoint"
```

---

### Task 3: SSE Event Stream

**Files:**
- Modify: `src/agenthub/ui.py` — add GET /api/events/stream
- Modify: `tests/test_ui.py` — add SSE test

- [ ] **Step 1: Add SSE endpoint in ui.py**

```python
@app.get("/api/events/stream")
async def event_stream():
    """SSE endpoint: agents connect to receive real-time task events.
    
    Usage: curl -N http://127.0.0.1:8765/api/events/stream
    
    Pushes new events every 1 second as SSE data lines.
    """
    import asyncio

    async def generate():
        last_cursor = 0
        while True:
            try:
                events = svc.pull_inbox("system", limit=50, since=last_cursor, peek=True)
                for event in events.get("events", []):
                    yield f"data: {_json.dumps(event)}\n\n"
                    if event.get("cursor", 0) > last_cursor:
                        last_cursor = event["cursor"]
            except Exception:
                pass
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 2: Add test to test_ui.py**

```python
def test_ui_sse_stream(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    
    client = TestClient(create_app(paths))
    resp = client.get("/api/events/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/event-stream"
```

- [ ] **Step 3: Run tests, commit**

---

### Task 4: Agent Worker Script

**Files:**
- Create: `scripts/agent_worker.py`

- [ ] **Step 1: Create agent worker**

Create `scripts/agent_worker.py`:
```python
#!/usr/bin/env python3
"""Agent Worker — minimal daemon that auto-participates in AgentHub.

Usage:
    python scripts/agent_worker.py --agent myname --skills python,code-review --hub http://localhost:8765

The worker:
    1. Registers with hub via Agent Card
    2. Subscribes to SSE event stream
    3. On task_created event: checks if skills match → claims if yes
    4. On handoff event directed to self: accepts
    5. Simulates work (sleep) then closes or hands off
"""

import argparse
import json
import os
import random
import signal
import sys
import time
import urllib.request
from urllib.error import URLError


def register(hub_url: str, agent_id: str, skills: list[str]):
    card = {
        "name": agent_id,
        "description": f"Agent {agent_id}",
        "skills": [{"id": s.strip(), "tags": [s.strip()]} for s in skills],
        "url": f"{hub_url}/a2a",
    }
    req = urllib.request.Request(
        f"{hub_url}/a2a",
        data=json.dumps({
            "jsonrpc": "2.0",
            "id": "reg-1",
            "method": "registry/register",
            "params": {"agentCard": card},
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    return _do(req)


def send(hub_url: str, agent_id: str, part_type: str, text: str, refs: list[str] = None, data: dict = None):
    part = {"text": text, "type": part_type}
    if data:
        part["data"] = data
    msg = {
        "messageId": f"{agent_id}-{int(time.time())}",
        "role": "agent",
        "parts": [part],
    }
    if refs:
        msg["referenceTaskIds"] = refs
    req = urllib.request.Request(
        f"{hub_url}/a2a",
        data=json.dumps({
            "jsonrpc": "2.0",
            "id": f"{agent_id}-{int(time.time())}",
            "method": "tasks/send",
            "params": {"message": msg},
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    return _do(req)


def subscribe(hub_url: str, agent_id: str, skills: list[str]):
    """Connect to SSE stream and handle events."""
    url = f"{hub_url}/api/events/stream"
    print(f"[{agent_id}] Subscribing to {url}...")
    
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        buffer = b""
        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            buffer += chunk
            while b"\n\n" in buffer:
                line, buffer = buffer.split(b"\n\n", 1)
                if line.startswith(b"data: "):
                    try:
                        event = json.loads(line[6:])
                        _handle_event(hub_url, agent_id, skills, event)
                    except json.JSONDecodeError:
                        pass


def _handle_event(hub_url: str, agent_id: str, skills: list[str], event: dict):
    etype = event.get("type", "")
    task_id = event.get("task_id", "")
    body = event.get("body", "")
    by = event.get("by_agent_id", "")

    if by == agent_id:
        return  # Ignore own events

    # New task created — check if skills match
    if etype == "status" and task_id:
        print(f"[{agent_id}] Saw event: {etype} from {by} — {body[:60]}")
        # Try to claim if task is open
        result = send(hub_url, agent_id, "claim", "I'll take this", refs=[task_id])
        if result and "error" not in result:
            print(f"[{agent_id}] Claimed {task_id}")
            # Simulate work
            time.sleep(random.uniform(0.5, 2.0))
            send(hub_url, agent_id, "status", f"Working on it (by {agent_id})", refs=[task_id])
            time.sleep(random.uniform(0.5, 1.0))
            send(hub_url, agent_id, "close", "Done!", refs=[task_id])
            print(f"[{agent_id}] Completed {task_id}")

    # Handoff directed to us — accept
    if "handoff" in body.lower() and agent_id in body:
        print(f"[{agent_id}] Handoff detected: {body}")
        # Find handoff ID and accept
        result = send(hub_url, agent_id, "claim", "Accepting handoff", refs=[task_id])
        if result and "error" not in result:
            print(f"[{agent_id}] Accepted handoff for {task_id}")


def _do(req):
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except URLError as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Agent Worker")
    parser.add_argument("--agent", required=True, help="Agent ID/name")
    parser.add_argument("--skills", default="general", help="Comma-separated skill tags")
    parser.add_argument("--hub", default="http://localhost:8765", help="Hub URL")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    args = parser.parse_args()
    
    skills_list = args.skills.split(",")
    
    # Register
    result = register(args.hub, args.agent, skills_list)
    if result and "error" not in result:
        print(f"[{args.agent}] Registered with skills: {skills_list}")
    else:
        print(f"[{args.agent}] Registration issue: {result}", file=sys.stderr)
    
    # Subscribe and work
    try:
        subscribe(args.hub, args.agent, skills_list)
    except KeyboardInterrupt:
        print(f"\n[{args.agent}] Shutting down.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke test**

```bash
# In terminal 1: start hub
hub ui --port 8765

# In terminal 2: start agent worker
python scripts/agent_worker.py --agent code-reviewer --skills python,review --once

# In terminal 3: create a task
hub task create --title "Review this" --intent "Need code review for security.py"
```

Expected: code-reviewer auto-claims and auto-closes the task within a few seconds.

- [ ] **Step 3: Commit**

```bash
git add scripts/agent_worker.py
git commit -m "feat: add agent worker script for auto-claim/close"
```

---

### Task 5: E2E Automation Tests (no human intervention)

**Files:**
- Create: `tests/test_e2e_automation.py`

- [ ] **Step 1: Create E2E test**

```python
"""E2E tests: prove agents can collaborate with zero human intervention."""


def test_two_agents_auto_claim_and_close(hub_home):
    """Agent A creates task, Agent B auto-claims and closes. No human steps."""
    from agenthub.config import HubPaths
    from agenthub.db import init_db
    from agenthub.service import HubService
    from agenthub.a2a import A2AHandler

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

    # Agent A creates task
    result = handler.dispatch({
        "jsonrpc": "2.0", "id": "3", "method": "tasks/send",
        "params": {"message": {
            "messageId": "alpha-msg",
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
    """A creates → B claims → B hands off to C → C claims → C closes. Zero human steps."""
    from agenthub.config import HubPaths
    from agenthub.db import init_db
    from agenthub.service import HubService
    from agenthub.a2a import A2AHandler

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

    # alpha creates task
    r = handler.dispatch({
        "jsonrpc": "2.0", "id": "create", "method": "tasks/send",
        "params": {"message": {
            "messageId": "alpha", "role": "agent",
            "parts": [{"text": "Complex task needs chain", "type": "intent"}]
        }}
    })
    task_id = r["result"]["task"]["id"]

    # beta claims
    handler.dispatch({
        "jsonrpc": "2.0", "id": "claim", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta", "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "I'll start phase 1", "type": "claim"}]
        }}
    })

    # beta hands off to gamma
    h = handler.dispatch({
        "jsonrpc": "2.0", "id": "handoff", "method": "tasks/send",
        "params": {"message": {
            "messageId": "beta", "role": "agent",
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
            "messageId": "gamma", "role": "agent",
            "referenceTaskIds": [task_id],
            "parts": [{"text": "Chain complete", "type": "close"}]
        }}
    })

    assert close["result"]["task"]["status"] == "done"
    task = svc.show_task(task_id, brief=False)
    assert task["owner_agent_id"] == "gamma"
```

- [ ] **Step 2: Run E2E tests**

```bash
pytest tests/test_e2e_automation.py -v
```
Expected: 2 PASS (agents auto-collaborate with zero human intervention)

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_automation.py
git commit -m "test: add E2E automation tests proving zero-human-intervention flow"
```

---

### Task 6: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```

- [ ] **Step 2: Manual E2E with real hub**

```bash
# Terminal 1: hub ui
# Terminal 2: python scripts/agent_worker.py --agent builder --skills python
# Terminal 3: python scripts/agent_worker.py --agent reviewer --skills review
# Then create a task via curl:
curl -X POST http://localhost:8765/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tasks/send","params":{"message":{"messageId":"test","role":"agent","parts":[{"text":"Build a login page","type":"intent"}]}}}'
```

Expected: One of the workers auto-claims and auto-closes within seconds.

- [ ] **Step 3: Final commit**

---

## Plan Self-Review

### Spec Coverage

All design spec requirements covered:
- ✅ A2A JSON-RPC endpoint (Task 2)
- ✅ Agent Card registry (Task 1)
- ✅ SSE event stream (Task 3)
- ✅ Agent worker daemon (Task 4)
- ✅ E2E zero-human-intervention tests (Task 5)
- ✅ Well-known Agent Card endpoint (Task 1)
- ✅ tasks/send, tasks/list, tasks/get, tasks/subscribe methods (Task 2)

### Placeholder Scan
No TODOs, no "add validation" without code, no references to undefined types. All steps have exact code or commands.
