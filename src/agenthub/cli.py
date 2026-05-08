from __future__ import annotations

import typer

from agenthub import __version__

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
def init() -> None:
    """Initialize a local AgentHub database."""
    typer.echo("init is not implemented yet")


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
    typer.echo("agent register is not implemented yet")


@task_app.command("list")
def task_list() -> None:
    typer.echo("task list is not implemented yet")


@event_app.command("push")
def event_push() -> None:
    typer.echo("event push is not implemented yet")


@inbox_app.command("pull")
def inbox_pull() -> None:
    typer.echo("inbox pull is not implemented yet")


def main() -> None:
    app()
