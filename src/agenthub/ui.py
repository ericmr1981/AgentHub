from __future__ import annotations

from importlib.resources import files

import jinja2
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agenthub.config import HubPaths
from agenthub.errors import HubError
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

    @app.get("/api/dashboard")
    def dashboard_api():
        try:
            return HubService(paths).dashboard_snapshot()
        except HubError as exc:
            return JSONResponse(status_code=500, content={"ok": False, "code": exc.code, "message": exc.message})

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        try:
            snapshot = HubService(paths).dashboard_snapshot()
        except HubError as exc:
            return HTMLResponse(content=f"<h1>AgentHub Error</h1><p>{exc.message}</p>", status_code=500)
        return templates.TemplateResponse(request, "index.html", {"snapshot": snapshot})

    return app


def run_ui(paths: HubPaths, host: str, port: int) -> None:
    uvicorn.run(create_app(paths), host=host, port=port)
