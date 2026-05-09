from __future__ import annotations

from fastapi.testclient import TestClient

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService
from agenthub.ui import create_app


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

    assert snapshot["radar"]["agents_total"] == 3
    assert snapshot["radar"]["agents_active"] == 1
    assert snapshot["radar"]["tasks_blocked"] == 0
    assert snapshot["tasks"][0]["id"] == "T000001"
    assert snapshot["timeline"][-1]["body"] == "visible"


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


def test_ui_management_actions(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.heartbeat_agent("codex", "active")
    task = service.create_task("Manage", "Test management", "normal", [])
    service.claim_task(task["id"], "codex")

    client = TestClient(create_app(paths))

    pause_resp = client.post("/api/agents/codex/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    resume_resp = client.post("/api/agents/codex/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "active"

    close_resp = client.post(f"/api/tasks/{task['id']}/close", json={"summary": "done via UI"})
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "done"


def test_ui_handoffs_page(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.register_agent("claude-code", "claude-code")
    task = service.create_task("HO", "Test", "normal", [])
    service.claim_task(task["id"], "codex")
    service.create_handoff(task["id"], "codex", "claude-code", "please review")

    client = TestClient(create_app(paths))
    resp = client.get("/handoffs")
    assert resp.status_code == 200
    assert "pending" in resp.text


def test_ui_health_page(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)

    client = TestClient(create_app(paths))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "hub.db" in resp.text


def test_ui_artifacts_api(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    client = TestClient(create_app(paths))
    resp = client.get("/api/artifacts")
    assert resp.status_code == 200
    assert "artifacts" in resp.json()


def test_ui_sse_stream(hub_home):
    """Test SSE stream endpoint via a real uvicorn server.

    Uses raw sockets (not TestClient) to avoid the ASGI-transport
    lifecycle deadlock inherent to infinite SSE generators.
    """
    import socket
    import threading
    import time

    import uvicorn

    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)

    app = create_app(paths)
    port = 19876

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(("127.0.0.1", port))
        sock.sendall(b"GET /api/events/stream HTTP/1.1\r\nHost: localhost\r\nAccept: text/event-stream\r\n\r\n")

        # Read the HTTP response line by line until we have all headers.
        # We use makefile() for line-buffered reading over the socket.
        f = sock.makefile("rb")
        status_line = f.readline()
        assert b"200" in status_line, f"Expected 200, got: {status_line.strip()}"

        headers = {}
        while True:
            line = f.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            if b":" in line:
                key, _, val = line.partition(b":")
                headers[key.strip().lower()] = val.strip()

        ct = headers.get(b"content-type", b"")
        assert b"text/event-stream" in ct, f"Expected text/event-stream, got: {ct}"
    finally:
        sock.close()
