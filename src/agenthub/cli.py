from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from agenthub import __version__
from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.errors import HubError
from agenthub.profiles import build_brief
from agenthub.service import HubService


def service_for(workspace: Path) -> HubService:
    return HubService(HubPaths.from_workspace(workspace))


def echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def echo_jsonl(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        echo_json(row)


def handle_error(exc: HubError) -> None:
    echo_json(exc.to_payload())
    raise typer.Exit(code=1)

app = typer.Typer(no_args_is_help=True, help="Local-first coordination hub for agents.")
agent_app = typer.Typer(help="Manage agent registry and heartbeats.")
task_app = typer.Typer(help="Manage task cards.")
event_app = typer.Typer(help="Push short coordination events.")
inbox_app = typer.Typer(help="Pull agent inbox events.")

app.add_typer(agent_app, name="agent")
app.add_typer(task_app, name="task")
app.add_typer(event_app, name="event")
app.add_typer(inbox_app, name="inbox")


@app.command()
def version() -> None:
    """Print AgentHub version."""
    typer.echo(f"AgentHub {__version__}")


@app.command()
def init(workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root for .agenthub.")) -> None:
    """Initialize a local AgentHub database."""
    paths = HubPaths.from_workspace(workspace)
    init_db(paths)
    typer.echo(f"Initialized AgentHub at {paths.db_path}")


@app.command()
def watch() -> None:
    """Watch inbox events as JSONL."""
    typer.echo("watch is not implemented yet")


@app.command()
def ui() -> None:
    """Start the local monitor UI."""
    typer.echo("ui is not implemented yet")


@app.command()
def brief(agent: str = typer.Option(..., "--agent"), format: str = typer.Option("md", "--format")) -> None:
    """Print a compact agent onboarding brief."""
    try:
        if format == "json":
            echo_json({"agent": agent, "brief": build_brief(agent)})
        else:
            typer.echo(build_brief(agent))
    except HubError as exc:
        handle_error(exc)


@app.command()
def doctor(agent: str = typer.Option(..., "--agent"), workspace: Path = typer.Option(Path("."), "--workspace")) -> None:
    """Validate agent registration and health."""
    try:
        echo_json(service_for(workspace).doctor_agent(agent))
    except HubError as exc:
        handle_error(exc)


@agent_app.command("register")
def agent_register(
    agent_id: str,
    profile: str = typer.Option(..., "--profile"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Register an agent in the hub."""
    try:
        echo_json(service_for(workspace).register_agent(agent_id, profile))
    except HubError as exc:
        handle_error(exc)


@agent_app.command("heartbeat")
def agent_heartbeat(
    agent_id: str,
    status: str = typer.Option("active", "--status"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Send a heartbeat for an agent."""
    try:
        echo_json(service_for(workspace).heartbeat_agent(agent_id, status))
    except HubError as exc:
        handle_error(exc)


@agent_app.command("list")
def agent_list(
    format: str = typer.Option("jsonl", "--format"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """List registered agents."""
    try:
        rows = service_for(workspace).list_agents()
    except HubError as exc:
        handle_error(exc)
        return
    if format == "jsonl":
        echo_jsonl(rows)
    else:
        echo_json(rows)


@agent_app.command("show")
def agent_show(
    agent_id: str,
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Show agent details."""
    try:
        echo_json(service_for(workspace).show_agent(agent_id))
    except HubError as exc:
        handle_error(exc)


@task_app.command("create")
def task_create(
    title: str = typer.Option(..., "--title"),
    intent: str = typer.Option(..., "--intent"),
    priority: str = typer.Option("normal", "--priority"),
    ref: list[str] = typer.Option([], "--ref"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Create a new task card."""
    refs = [{"kind": "file", "uri": item, "summary": ""} for item in ref]
    try:
        echo_json(service_for(workspace).create_task(title, intent, priority, refs))
    except HubError as exc:
        handle_error(exc)


@task_app.command("list")
def task_list(
    status: str | None = typer.Option(None, "--status"),
    format: str = typer.Option("jsonl", "--format"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """List task cards."""
    try:
        rows = service_for(workspace).list_tasks(status=status)
    except HubError as exc:
        handle_error(exc)
        return
    if format == "jsonl":
        echo_jsonl(rows)
    else:
        echo_json(rows)


@task_app.command("show")
def task_show(
    task_id: str,
    brief: bool = typer.Option(False, "--brief"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Show task details."""
    try:
        echo_json(service_for(workspace).show_task(task_id, brief=brief))
    except HubError as exc:
        handle_error(exc)


@task_app.command("claim")
def task_claim(
    task_id: str,
    agent: str = typer.Option(..., "--agent"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Claim ownership of a task."""
    try:
        echo_json(service_for(workspace).claim_task(task_id, agent))
    except HubError as exc:
        handle_error(exc)


@event_app.command("push")
def event_push(
    task: str | None = typer.Option(None, "--task"),
    agent: str = typer.Option(..., "--agent"),
    type: str = typer.Option(..., "--type"),
    body: str = typer.Option(..., "--body"),
    ref: list[str] = typer.Option([], "--ref"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Push a short coordination event."""
    refs = [{"kind": "file", "uri": item, "summary": ""} for item in ref]
    try:
        echo_json(service_for(workspace).push_event(task, agent, type, body, refs))
    except HubError as exc:
        handle_error(exc)


@inbox_app.command("pull")
def inbox_pull(
    agent: str = typer.Option(..., "--agent"),
    limit: int = typer.Option(10, "--limit"),
    since: int | None = typer.Option(None, "--since"),
    format: str = typer.Option("jsonl", "--format"),
    peek: bool = typer.Option(False, "--peek"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Pull agent inbox events."""
    try:
        payload = service_for(workspace).pull_inbox(agent, limit, since, peek)
    except HubError as exc:
        handle_error(exc)
        return
    if format == "jsonl":
        echo_jsonl(payload["events"])
    else:
        echo_json(payload)


def main() -> None:
    app()
