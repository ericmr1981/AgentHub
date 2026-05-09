from __future__ import annotations

import asyncio
import json as _json
import os
from datetime import datetime, timezone
from importlib.resources import files

import jinja2
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agenthub.a2a import A2AHandler
from agenthub.config import HubPaths
from agenthub.errors import HubError
from agenthub.models import STALE_HEARTBEAT_SECONDS
from agenthub.service import HubService


def create_app(paths: HubPaths) -> FastAPI:
    app = FastAPI(title="AgentHub Monitor")
    package_files = files("agenthub")
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(package_files / "templates")),
        auto_reload=False,
    )
    templates = Jinja2Templates(env=jinja_env)
    app.mount("/static", StaticFiles(directory=str(package_files / "static")), name="static")
    svc = HubService(paths)
    a2a = A2AHandler(svc)

    @app.get("/api/dashboard")
    def dashboard_api():
        try:
            return svc.dashboard_snapshot()
        except HubError as exc:
            return JSONResponse(status_code=500, content={"ok": False, "code": exc.code, "message": exc.message})

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        try:
            snapshot = svc.dashboard_snapshot()
        except HubError as exc:
            return HTMLResponse(content=f"<h1>AgentHub Error</h1><p>{exc.message}</p>", status_code=500)
        return templates.TemplateResponse(request, "index.html", {"snapshot": snapshot})

    @app.post("/api/agents/{agent_id}/pause")
    def agent_pause(agent_id: str):
        try:
            return svc.pause_agent(agent_id)
        except HubError as exc:
            return JSONResponse(status_code=404 if exc.code == "AGENT_NOT_FOUND" else 400, content={"ok": False, "error": exc.message})

    @app.post("/api/agents/{agent_id}/resume")
    def agent_resume(agent_id: str):
        try:
            return svc.resume_agent(agent_id)
        except HubError as exc:
            return JSONResponse(status_code=404 if exc.code == "AGENT_NOT_FOUND" else 400, content={"ok": False, "error": exc.message})

    @app.post("/api/tasks/{task_id}/close")
    def task_close(task_id: str, body: dict | None = None):
        summary = (body or {}).get("summary", "closed via UI")
        try:
            snapshot = svc.dashboard_snapshot()
            agent_id = "unknown"
            for t in snapshot["tasks"]:
                if t["id"] == task_id and t.get("owner_agent_id"):
                    agent_id = t["owner_agent_id"]
                    break
            return svc.close_task(task_id, agent_id, summary)
        except HubError as exc:
            return JSONResponse(status_code=404, content={"ok": False, "error": exc.message})

    @app.post("/api/tasks/{task_id}/reassign")
    def task_reassign(task_id: str, body: dict | None = None):
        agent_id = (body or {}).get("agent_id", "")
        try:
            return svc.reassign_task(task_id, agent_id)
        except HubError as exc:
            return JSONResponse(status_code=404, content={"ok": False, "error": exc.message})

    @app.get("/api/handoffs")
    def handoffs_api(status: str | None = None):
        try:
            return {"handoffs": svc.list_handoffs(status=status)}
        except HubError as exc:
            return JSONResponse(status_code=500, content={"ok": False, "error": exc.message})

    @app.get("/api/artifacts")
    def artifacts_api():
        try:
            snapshot = svc.dashboard_snapshot()
            artifacts = []
            for task in snapshot["tasks"]:
                refs_raw = task.get("refs_json", "[]")
                refs = _json.loads(refs_raw) if isinstance(refs_raw, str) else refs_raw
                for ref in refs:
                    artifacts.append({"task_id": task["id"], **ref})
            return {"artifacts": artifacts}
        except HubError as exc:
            return JSONResponse(status_code=500, content={"ok": False, "error": exc.message})

    @app.get("/api/health")
    def health_api():
        try:
            db_path = paths.db_path
            snapshot = svc.dashboard_snapshot()
            stale_count = 0
            for agent_snapshot in snapshot["agents"]:
                if agent_snapshot["status"] == "active" and agent_snapshot["last_seen_at"]:
                    try:
                        last = datetime.fromisoformat(agent_snapshot["last_seen_at"])
                        if (datetime.now(timezone.utc) - last).total_seconds() > STALE_HEARTBEAT_SECONDS:
                            stale_count += 1
                    except (ValueError, TypeError):
                        stale_count += 1
            return {
                "db_path": str(db_path),
                "db_size_bytes": os.path.getsize(db_path) if db_path.exists() else 0,
                "event_count": len(snapshot["timeline"]),
                "agent_count": snapshot["radar"]["agents_total"],
                "stale_agents": stale_count,
            }
        except HubError as exc:
            return JSONResponse(status_code=500, content={"ok": False, "error": exc.message})

    @app.get("/handoffs", response_class=HTMLResponse)
    def handoffs_page(request: Request):
        try:
            handoffs = svc.list_handoffs()
            return templates.TemplateResponse(request, "handoffs.html", {"handoffs": handoffs})
        except HubError as exc:
            return HTMLResponse(content=f"<h1>Error</h1><p>{exc.message}</p>", status_code=500)

    @app.get("/health", response_class=HTMLResponse)
    def health_page(request: Request):
        try:
            db_path = paths.db_path
            db_size = os.path.getsize(db_path) if db_path.exists() else 0
            snapshot = svc.dashboard_snapshot()
            stale_agents = []
            for a in snapshot["agents"]:
                if a["status"] == "active" and a["last_seen_at"]:
                    try:
                        last = datetime.fromisoformat(a["last_seen_at"])
                        if (datetime.now(timezone.utc) - last).total_seconds() > STALE_HEARTBEAT_SECONDS:
                            stale_agents.append(a)
                    except (ValueError, TypeError):
                        stale_agents.append(a)
            return templates.TemplateResponse(request, "health.html", {
                "db_path": str(db_path),
                "db_size": db_size,
                "event_count": len(snapshot["timeline"]),
                "agent_count": snapshot["radar"]["agents_total"],
                "stale_agents": stale_agents,
            })
        except HubError as exc:
            return HTMLResponse(content=f"<h1>Error</h1><p>{exc.message}</p>", status_code=500)

    @app.get("/onboarding", response_class=HTMLResponse)
    def onboarding_page(request: Request):
        return templates.TemplateResponse(request, "onboarding.html", {})

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

    @app.post("/a2a")
    async def a2a_endpoint(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
        result = a2a.dispatch(body)
        return result

    @app.get("/api/events/stream")
    async def event_stream():
        """SSE endpoint: agents connect to receive real-time task events.

        Usage: curl -N http://localhost:8765/api/events/stream

        Pushes new events every 1 second as SSE data lines.
        """
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

    return app


def run_ui(paths: HubPaths, host: str, port: int) -> None:
    uvicorn.run(create_app(paths), host=host, port=port)
