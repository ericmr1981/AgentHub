from __future__ import annotations

from importlib.resources import files

import jinja2
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agenthub.config import HubPaths
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
        return HubService(paths).dashboard_snapshot()

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        snapshot = HubService(paths).dashboard_snapshot()
        return templates.TemplateResponse(request, "index.html", {"snapshot": snapshot})

    return app


def run_ui(paths: HubPaths, host: str, port: int) -> None:
    uvicorn.run(create_app(paths), host=host, port=port)
