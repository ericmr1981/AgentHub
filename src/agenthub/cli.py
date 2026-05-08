from __future__ import annotations

from pathlib import Path

import typer

from agenthub import __version__
from agenthub.config import HubPaths
from agenthub.db import init_db

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


@agent_app.command("register")
def agent_register() -> None:
    """Register an agent in the hub."""
    typer.echo("agent register is not implemented yet")


@agent_app.command("heartbeat")
def agent_heartbeat() -> None:
    """Send a heartbeat for an agent."""
    typer.echo("agent heartbeat is not implemented yet")


@task_app.command("create")
def task_create() -> None:
    """Create a new task card."""
    typer.echo("task create is not implemented yet")


@task_app.command("list")
def task_list() -> None:
    """List task cards."""
    typer.echo("task list is not implemented yet")


@event_app.command("push")
def event_push() -> None:
    """Push a short coordination event."""
    typer.echo("event push is not implemented yet")


@inbox_app.command("pull")
def inbox_pull() -> None:
    """Pull agent inbox events."""
    typer.echo("inbox pull is not implemented yet")


def main() -> None:
    app()
