# AgentHub MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first local AgentHub vertical slice: SQLite-backed Python CLI, agent onboarding commands, task/event/inbox coordination, and a read-only local monitor UI.

**Architecture:** AgentHub is a local-first Python package. A shared service layer owns SQLite persistence and domain mutations; Typer exposes it through a `hub` CLI; FastAPI exposes read-only monitor endpoints and server-rendered HTML for Radar, Tasks, and Timeline. SQLite remains the single source of truth in `.agenthub/hub.db`.

**Tech Stack:** Python 3.11+, SQLite stdlib, Typer, FastAPI, Uvicorn, Jinja2, Pytest, HTTPX/TestClient, Ruff optional for linting.

---

## Scope

This plan implements the MVP from `docs/superpowers/specs/2026-05-08-agenthub-local-design.md`:

- `hub init`
- `hub agent register`, `heartbeat`, `list`, `show`
- `hub brief`, `hub doctor`
- `hub task create`, `list`, `show`, `claim`
- `hub event push`
- `hub inbox pull`
- `hub watch` with bounded testable loop support
- `hub ui` with read-only Radar, Tasks, and Timeline
- Default profiles for `codex`, `claude-code`, `openclaw`, and `hermes`

This plan intentionally does not implement compaction, native OpenClaw/Hermes plugins, UI write actions, or advanced archival. Those are post-MVP plans.

## File Map

Create these files:

- `pyproject.toml`: package metadata, console script, dependencies, pytest config.
- `README.md`: quick start and core commands.
- `src/agenthub/__init__.py`: package version.
- `src/agenthub/__main__.py`: `python -m agenthub` entrypoint.
- `src/agenthub/cli.py`: Typer command tree and stdout/stderr formatting.
- `src/agenthub/config.py`: Hub path resolution and `.agenthub` directory handling.
- `src/agenthub/db.py`: SQLite connection, schema creation, WAL setup, transactions.
- `src/agenthub/models.py`: dataclasses and JSON helpers.
- `src/agenthub/profiles.py`: default runtime profiles and brief prompt text.
- `src/agenthub/service.py`: domain operations for agents, tasks, events, inbox, dashboard queries.
- `src/agenthub/errors.py`: structured error classes and CLI serialization.
- `src/agenthub/ui.py`: FastAPI app factory and `hub ui` runner.
- `src/agenthub/templates/base.html`: shared UI shell.
- `src/agenthub/templates/index.html`: Radar, Tasks, Timeline page.
- `src/agenthub/static/app.css`: industrial control tower styling.
- `tests/conftest.py`: temp Hub fixture and CLI runner helpers.
- `tests/test_db.py`: initialization and WAL tests.
- `tests/test_agents.py`: register, heartbeat, list, show, brief, doctor tests.
- `tests/test_tasks_events_inbox.py`: task/event/inbox/claim tests.
- `tests/test_cli_jsonl.py`: CLI output and error tests.
- `tests/test_ui.py`: FastAPI dashboard endpoint and page tests.
- `tests/test_load_smoke.py`: 1,000 short event smoke test.

## Domain Conventions

Use these exact statuses and event types in implementation:

```python
AGENT_STATUSES = {"active", "idle", "paused", "stale"}
TASK_STATUSES = {"open", "claimed", "blocked", "done", "archived"}
EVENT_TYPES = {"status", "claim", "handoff", "blocked", "note", "artifact", "heartbeat"}
HANDOFF_STATUSES = {"pending", "accepted", "stale"}
```

Use monotonic integer primary keys internally and public IDs with prefixes:

```text
agents.id: user-provided text, e.g. codex
Tasks: T000001
Events: E000001
Handoffs: H000001
```

Use ISO timestamps with timezone in UTC:

```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
```

---

### Task 1: Package Skeleton and CLI Entrypoint

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/agenthub/__init__.py`
- Create: `src/agenthub/__main__.py`
- Create: `src/agenthub/cli.py`
- Create: `tests/conftest.py`
- Create: `tests/test_cli_jsonl.py`

- [ ] **Step 1: Write failing CLI smoke tests**

Create `tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agenthub.cli import app


class HubCliRunner:
    def __init__(self) -> None:
        self._runner = CliRunner()

    def invoke(self, args: list[str]):
        return self._runner.invoke(app, args)


@pytest.fixture()
def runner() -> HubCliRunner:
    return HubCliRunner()


@pytest.fixture()
def hub_home(tmp_path: Path) -> Path:
    return tmp_path / "workspace"
```

Create `tests/test_cli_jsonl.py`:

```python
from __future__ import annotations


def test_version_command_outputs_version(runner):
    result = runner.invoke(["version"])

    assert result.exit_code == 0
    assert "AgentHub" in result.stdout


def test_root_help_lists_core_commands(runner):
    result = runner.invoke(["--help"])

    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "agent" in result.stdout
    assert "task" in result.stdout
    assert "event" in result.stdout
    assert "inbox" in result.stdout
    assert "watch" in result.stdout
    assert "ui" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_cli_jsonl.py -v
```

Expected: FAIL during import because `agenthub.cli` does not exist.

- [ ] **Step 3: Create package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agenthub-local"
version = "0.1.0"
description = "Local-first coordination hub for agent collaboration."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12,<1.0",
  "fastapi>=0.111,<1.0",
  "uvicorn>=0.30,<1.0",
  "jinja2>=3.1,<4.0",
  "python-multipart>=0.0.9,<1.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2,<9.0",
  "httpx>=0.27,<1.0",
  "ruff>=0.5,<1.0",
]

[project.scripts]
hub = "agenthub.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
agenthub = ["templates/*.html", "static/*.css"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Create `README.md`:

````markdown
# AgentHub

AgentHub is a local-first coordination hub for multiple agents. It uses short structured events, task cards, artifact references, and a local monitor UI.

## MVP Quick Start

```bash
hub init
hub agent register codex --profile codex
hub agent heartbeat codex --status active
hub task create --title "Wire CLI" --intent "Build the first CLI path" --priority normal
hub task list --format jsonl
```
````

- [ ] **Step 4: Create minimal CLI app**

Create `src/agenthub/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/agenthub/__main__.py`:

```python
from agenthub.cli import main

if __name__ == "__main__":
    main()
```

Create `src/agenthub/cli.py`:

```python
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
```

- [ ] **Step 5: Run CLI smoke tests**

Run:

```bash
pytest tests/test_cli_jsonl.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit package skeleton**

```bash
git add pyproject.toml README.md src tests/conftest.py tests/test_cli_jsonl.py
git commit -m "feat: add AgentHub package skeleton"
```

---

### Task 2: SQLite Configuration and Schema

**Files:**
- Create: `src/agenthub/config.py`
- Create: `src/agenthub/db.py`
- Create: `tests/test_db.py`
- Modify: `src/agenthub/cli.py`

- [ ] **Step 1: Write failing database tests**

Create `tests/test_db.py`:

```python
from __future__ import annotations

import sqlite3

from agenthub.config import HubPaths
from agenthub.db import connect, init_db


def test_init_db_creates_schema_and_wal(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)

    assert paths.hub_dir.exists()
    assert paths.db_path.exists()

    with connect(paths) as conn:
        table_names = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type = 'table'")
        }
        assert "agents" in table_names
        assert "tasks" in table_names
        assert "events" in table_names
        assert "inbox_offsets" in table_names
        assert "handoffs" in table_names
        assert "compactions" in table_names
        journal_mode = conn.execute("pragma journal_mode").fetchone()[0]
        assert journal_mode == "wal"


def test_connect_returns_rows_as_mappings(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)

    with connect(paths) as conn:
        row = conn.execute("select 1 as value").fetchone()

    assert isinstance(row, sqlite3.Row)
    assert row["value"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_db.py -v
```

Expected: FAIL because `agenthub.config` and `agenthub.db` do not exist.

- [ ] **Step 3: Implement path configuration**

Create `src/agenthub/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HubPaths:
    workspace: Path
    hub_dir: Path
    db_path: Path

    @classmethod
    def from_workspace(cls, workspace: Path | str = ".") -> "HubPaths":
        root = Path(workspace).expanduser().resolve()
        hub_dir = root / ".agenthub"
        return cls(workspace=root, hub_dir=hub_dir, db_path=hub_dir / "hub.db")
```

- [ ] **Step 4: Implement SQLite schema**

Create `src/agenthub/db.py`:

```python
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from agenthub.config import HubPaths

SCHEMA = """
create table if not exists agents (
    id text primary key,
    display_name text not null,
    profile_name text not null,
    status text not null,
    last_seen_at text,
    metadata_json text not null default '{}'
);

create table if not exists tasks (
    pk integer primary key autoincrement,
    id text unique,
    title text not null,
    intent text not null,
    status text not null,
    owner_agent_id text,
    priority text not null,
    created_at text not null,
    updated_at text not null,
    closed_at text,
    refs_json text not null default '[]',
    summary text,
    foreign key(owner_agent_id) references agents(id)
);

create table if not exists events (
    pk integer primary key autoincrement,
    id text unique,
    task_id text,
    type text not null,
    by_agent_id text not null,
    body text not null,
    refs_json text not null default '[]',
    cursor integer unique,
    created_at text not null,
    foreign key(task_id) references tasks(id),
    foreign key(by_agent_id) references agents(id)
);

create table if not exists inbox_offsets (
    agent_id text primary key,
    last_cursor integer not null default 0,
    foreign key(agent_id) references agents(id)
);

create table if not exists handoffs (
    pk integer primary key autoincrement,
    id text unique,
    task_id text not null,
    from_agent_id text not null,
    to_agent_id text not null,
    reason text not null,
    status text not null,
    created_at text not null,
    accepted_at text,
    foreign key(task_id) references tasks(id),
    foreign key(from_agent_id) references agents(id),
    foreign key(to_agent_id) references agents(id)
);

create table if not exists compactions (
    pk integer primary key autoincrement,
    id text unique,
    scope text not null,
    summary text not null,
    source_event_start integer not null,
    source_event_end integer not null,
    created_at text not null
);

create index if not exists idx_tasks_status on tasks(status);
create index if not exists idx_tasks_owner on tasks(owner_agent_id);
create index if not exists idx_events_cursor on events(cursor);
create index if not exists idx_events_task on events(task_id);
create index if not exists idx_events_agent on events(by_agent_id);
"""


@contextmanager
def connect(paths: HubPaths) -> Iterator[sqlite3.Connection]:
    paths.hub_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(paths.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(paths: HubPaths) -> None:
    paths.hub_dir.mkdir(parents=True, exist_ok=True)
    with connect(paths) as conn:
        conn.execute("pragma journal_mode = wal")
        conn.executescript(SCHEMA)
```

- [ ] **Step 5: Wire `hub init` to schema creation**

Modify `src/agenthub/cli.py` imports and `init` command:

```python
from pathlib import Path

from agenthub.config import HubPaths
from agenthub.db import init_db
```

Replace `init` with:

```python
@app.command()
def init(workspace: Path = typer.Option(Path("."), "--workspace", help="Workspace root for .agenthub.")) -> None:
    """Initialize a local AgentHub database."""
    paths = HubPaths.from_workspace(workspace)
    init_db(paths)
    typer.echo(f"Initialized AgentHub at {paths.db_path}")
```

- [ ] **Step 6: Run database tests**

Run:

```bash
pytest tests/test_db.py -v
```

Expected: PASS.

- [ ] **Step 7: Run full current test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit schema work**

```bash
git add src/agenthub/config.py src/agenthub/db.py src/agenthub/cli.py tests/test_db.py
git commit -m "feat: initialize SQLite hub schema"
```

---

### Task 3: Models, Profiles, and Structured Errors

**Files:**
- Create: `src/agenthub/models.py`
- Create: `src/agenthub/profiles.py`
- Create: `src/agenthub/errors.py`
- Create: `tests/test_agents.py`

- [ ] **Step 1: Write failing tests for profiles and errors**

Create `tests/test_agents.py`:

```python
from __future__ import annotations

import json

from agenthub.errors import HubError
from agenthub.profiles import DEFAULT_PROFILES, build_brief


def test_default_profiles_include_first_class_agents():
    assert {"codex", "claude-code", "openclaw", "hermes"}.issubset(DEFAULT_PROFILES)
    assert DEFAULT_PROFILES["codex"].event_body_budget_chars == 280
    assert DEFAULT_PROFILES["codex"].preferred_format == "jsonl"


def test_build_brief_mentions_low_token_rules():
    brief = build_brief("codex")

    assert "AgentHub" in brief
    assert "280" in brief
    assert "hub inbox pull --agent codex" in brief
    assert "refs" in brief


def test_hub_error_serializes_to_json_shape():
    error = HubError("TASK_NOT_FOUND", "Task T000999 was not found", "Run hub task list.")

    payload = error.to_payload()

    assert payload == {
        "ok": False,
        "error": {
            "code": "TASK_NOT_FOUND",
            "message": "Task T000999 was not found",
            "hint": "Run hub task list.",
        },
    }
    json.dumps(payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_agents.py -v
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement dataclasses and JSON helpers**

Create `src/agenthub/models.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

AGENT_STATUSES = {"active", "idle", "paused", "stale"}
TASK_STATUSES = {"open", "claimed", "blocked", "done", "archived"}
EVENT_TYPES = {"status", "claim", "handoff", "blocked", "note", "artifact", "heartbeat"}
HANDOFF_STATUSES = {"pending", "accepted", "stale"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


@dataclass(frozen=True)
class Profile:
    id: str
    display_name: str
    inbox_limit: int
    watch_interval_ms: int
    event_body_budget_chars: int
    preferred_format: str
    supports_shell: bool
    supports_plugin: bool
    prompt_snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Implement structured errors**

Create `src/agenthub/errors.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HubError(Exception):
    code: str
    message: str
    hint: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.hint:
            payload["error"]["hint"] = self.hint
        return payload
```

- [ ] **Step 5: Implement default profiles and brief builder**

Create `src/agenthub/profiles.py`:

```python
from __future__ import annotations

from agenthub.errors import HubError
from agenthub.models import EVENT_TYPES, Profile

PROMPT_SNIPPET = (
    "You coordinate through AgentHub. Use short structured events, keep bodies under "
    "280 characters, and put large content in refs. Pull your inbox with `hub inbox "
    "pull --agent <id> --limit 10 --format jsonl`. Claim work before editing, publish "
    "status events as you progress, and use handoff when another agent should continue."
)

DEFAULT_PROFILES: dict[str, Profile] = {
    "codex": Profile("codex", "Codex", 10, 1000, 280, "jsonl", True, False, PROMPT_SNIPPET),
    "claude-code": Profile("claude-code", "Claude Code", 10, 1000, 280, "jsonl", True, False, PROMPT_SNIPPET),
    "openclaw": Profile("openclaw", "OpenClaw", 10, 1000, 280, "jsonl", True, True, PROMPT_SNIPPET),
    "hermes": Profile("hermes", "Hermes Agent", 10, 1000, 280, "jsonl", True, True, PROMPT_SNIPPET),
}


def get_profile(profile_id: str) -> Profile:
    try:
        return DEFAULT_PROFILES[profile_id]
    except KeyError as exc:
        raise HubError("PROFILE_NOT_FOUND", f"Profile {profile_id} was not found", "Run hub brief --agent codex for a known profile.") from exc


def build_brief(agent_id: str, profile_id: str | None = None) -> str:
    profile = get_profile(profile_id or agent_id)
    event_types = ", ".join(sorted(EVENT_TYPES))
    return "\n".join(
        [
            f"# AgentHub brief for {agent_id}",
            "",
            f"Profile: {profile.id} ({profile.display_name})",
            f"Event body budget: {profile.event_body_budget_chars} characters",
            f"Preferred format: {profile.preferred_format}",
            "",
            "Recommended inbox command:",
            f"hub inbox pull --agent {agent_id} --limit {profile.inbox_limit} --format jsonl",
            "",
            "Recommended watch command:",
            f"hub watch --agent {agent_id} --interval {profile.watch_interval_ms}ms --format jsonl",
            "",
            f"Allowed event types: {event_types}",
            "",
            "Low-token rule: keep event bodies short and put large content in refs.",
            "",
            "Minimal flow:",
            "hub task list --status open --format jsonl",
            f"hub task claim T000001 --agent {agent_id}",
            f"hub event push --task T000001 --agent {agent_id} --type status --body \"started\"",
            f"hub handoff T000001 --from {agent_id} --to claude-code --reason \"please review\"",
            "",
            profile.prompt_snippet,
        ]
    )
```

- [ ] **Step 6: Run profile and error tests**

Run:

```bash
pytest tests/test_agents.py -v
```

Expected: PASS.

- [ ] **Step 7: Run full current test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit profiles and errors**

```bash
git add src/agenthub/models.py src/agenthub/profiles.py src/agenthub/errors.py tests/test_agents.py
git commit -m "feat: add profiles and structured errors"
```

---

### Task 4: Agent Registry Service and CLI

**Files:**
- Create: `src/agenthub/service.py`
- Modify: `src/agenthub/cli.py`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Add failing service tests for agent registry**

Append to `tests/test_agents.py`:

```python
from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


def test_register_heartbeat_list_and_show_agent(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)

    agent = service.register_agent("codex", "codex")
    service.heartbeat_agent("codex", "active")
    agents = service.list_agents()
    shown = service.show_agent("codex")

    assert agent["id"] == "codex"
    assert shown["status"] == "active"
    assert shown["profile_name"] == "codex"
    assert shown["last_seen_at"] is not None
    assert [item["id"] for item in agents] == ["codex"]


def test_doctor_reports_registered_agent(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.heartbeat_agent("codex", "active")

    report = service.doctor_agent("codex")

    assert report["ok"] is True
    assert report["checks"]["database"] is True
    assert report["checks"]["registered"] is True
    assert report["checks"]["profile"] is True
    assert report["agent"]["id"] == "codex"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_agents.py::test_register_heartbeat_list_and_show_agent tests/test_agents.py::test_doctor_reports_registered_agent -v
```

Expected: FAIL because `HubService` does not exist.

- [ ] **Step 3: Implement agent service methods**

Create `src/agenthub/service.py`:

```python
from __future__ import annotations

from typing import Any

from agenthub.config import HubPaths
from agenthub.db import connect
from agenthub.errors import HubError
from agenthub.models import AGENT_STATUSES, dumps_json, utc_now
from agenthub.profiles import get_profile


class HubService:
    def __init__(self, paths: HubPaths):
        self.paths = paths

    def register_agent(self, agent_id: str, profile_name: str) -> dict[str, Any]:
        profile = get_profile(profile_name)
        now = utc_now()
        with connect(self.paths) as conn:
            conn.execute(
                """
                insert into agents (id, display_name, profile_name, status, last_seen_at, metadata_json)
                values (?, ?, ?, 'idle', ?, ?)
                on conflict(id) do update set
                    display_name = excluded.display_name,
                    profile_name = excluded.profile_name
                """,
                (agent_id, profile.display_name, profile_name, now, dumps_json({})),
            )
            conn.execute(
                "insert or ignore into inbox_offsets (agent_id, last_cursor) values (?, 0)",
                (agent_id,),
            )
        return self.show_agent(agent_id)

    def heartbeat_agent(self, agent_id: str, status: str) -> dict[str, Any]:
        if status not in AGENT_STATUSES:
            raise HubError("INVALID_AGENT_STATUS", f"Agent status {status} is invalid", f"Use one of {sorted(AGENT_STATUSES)}.")
        now = utc_now()
        with connect(self.paths) as conn:
            result = conn.execute(
                "update agents set status = ?, last_seen_at = ? where id = ?",
                (status, now, agent_id),
            )
            if result.rowcount == 0:
                raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Run hub agent register first.")
        return self.show_agent(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        with connect(self.paths) as conn:
            rows = conn.execute(
                "select id, display_name, profile_name, status, last_seen_at, metadata_json from agents order by id"
            ).fetchall()
        return [dict(row) for row in rows]

    def show_agent(self, agent_id: str) -> dict[str, Any]:
        with connect(self.paths) as conn:
            row = conn.execute(
                "select id, display_name, profile_name, status, last_seen_at, metadata_json from agents where id = ?",
                (agent_id,),
            ).fetchone()
        if row is None:
            raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Run hub agent list.")
        return dict(row)

    def doctor_agent(self, agent_id: str) -> dict[str, Any]:
        database_ok = self.paths.db_path.exists()
        try:
            agent = self.show_agent(agent_id)
            registered = True
        except HubError:
            agent = None
            registered = False
        profile_ok = bool(agent and agent["profile_name"])
        heartbeat_ok = bool(agent and agent["last_seen_at"])
        return {
            "ok": database_ok and registered and profile_ok and heartbeat_ok,
            "agent": agent,
            "checks": {
                "database": database_ok,
                "registered": registered,
                "profile": profile_ok,
                "heartbeat": heartbeat_ok,
            },
        }
```

- [ ] **Step 4: Run registry service tests**

Run:

```bash
pytest tests/test_agents.py::test_register_heartbeat_list_and_show_agent tests/test_agents.py::test_doctor_reports_registered_agent -v
```

Expected: PASS.

- [ ] **Step 5: Wire CLI formatting helpers and agent commands**

Modify `src/agenthub/cli.py` to include these imports:

```python
import json
from typing import Any

from agenthub.errors import HubError
from agenthub.profiles import build_brief
from agenthub.service import HubService
```

Add helpers near the top:

```python
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
```

Replace agent command stubs with:

```python
@agent_app.command("register")
def agent_register(
    agent_id: str,
    profile: str = typer.Option(..., "--profile"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
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
    try:
        echo_json(service_for(workspace).heartbeat_agent(agent_id, status))
    except HubError as exc:
        handle_error(exc)


@agent_app.command("list")
def agent_list(
    format: str = typer.Option("jsonl", "--format"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    rows = service_for(workspace).list_agents()
    if format == "jsonl":
        echo_jsonl(rows)
    else:
        echo_json(rows)


@agent_app.command("show")
def agent_show(
    agent_id: str,
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    try:
        echo_json(service_for(workspace).show_agent(agent_id))
    except HubError as exc:
        handle_error(exc)


@app.command()
def brief(agent: str = typer.Option(..., "--agent"), format: str = typer.Option("md", "--format")) -> None:
    try:
        if format == "json":
            echo_json({"agent": agent, "brief": build_brief(agent)})
        else:
            typer.echo(build_brief(agent))
    except HubError as exc:
        handle_error(exc)


@app.command()
def doctor(agent: str = typer.Option(..., "--agent"), workspace: Path = typer.Option(Path("."), "--workspace")) -> None:
    echo_json(service_for(workspace).doctor_agent(agent))
```

- [ ] **Step 6: Add CLI tests for agent commands**

Append to `tests/test_cli_jsonl.py`:

```python
import json


def test_agent_register_and_list_cli(runner, hub_home):
    init_result = runner.invoke(["init", "--workspace", str(hub_home)])
    assert init_result.exit_code == 0

    register_result = runner.invoke([
        "agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)
    ])
    assert register_result.exit_code == 0
    registered = json.loads(register_result.stdout)
    assert registered["id"] == "codex"

    list_result = runner.invoke(["agent", "list", "--workspace", str(hub_home)])
    assert list_result.exit_code == 0
    rows = [json.loads(line) for line in list_result.stdout.splitlines()]
    assert rows[0]["id"] == "codex"


def test_brief_cli_outputs_profile_help(runner):
    result = runner.invoke(["brief", "--agent", "codex"])

    assert result.exit_code == 0
    assert "AgentHub brief for codex" in result.stdout
    assert "hub inbox pull --agent codex" in result.stdout
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/test_agents.py tests/test_cli_jsonl.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit agent registry work**

```bash
git add src/agenthub/service.py src/agenthub/cli.py tests/test_agents.py tests/test_cli_jsonl.py
git commit -m "feat: add agent registry commands"
```

---

### Task 5: Task Creation, Listing, Showing, and Atomic Claim

**Files:**
- Modify: `src/agenthub/service.py`
- Modify: `src/agenthub/cli.py`
- Create: `tests/test_tasks_events_inbox.py`

- [ ] **Step 1: Write failing task service tests**

Create `tests/test_tasks_events_inbox.py`:

```python
from __future__ import annotations

import pytest

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.errors import HubError
from agenthub.service import HubService


@pytest.fixture()
def service(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    hub = HubService(paths)
    hub.register_agent("codex", "codex")
    hub.register_agent("claude-code", "claude-code")
    return hub


def test_create_list_show_and_claim_task(service):
    task = service.create_task("Wire CLI", "Build CLI path", "normal", [])
    listed = service.list_tasks(status="open")
    claimed = service.claim_task(task["id"], "codex")
    shown = service.show_task(task["id"], brief=True)

    assert task["id"] == "T000001"
    assert listed[0]["title"] == "Wire CLI"
    assert claimed["status"] == "claimed"
    assert claimed["owner_agent_id"] == "codex"
    assert shown["recent_events"][-1]["type"] == "claim"


def test_claim_task_is_atomic(service):
    task = service.create_task("Race", "Only one owner", "normal", [])
    service.claim_task(task["id"], "codex")

    with pytest.raises(HubError) as exc:
        service.claim_task(task["id"], "claude-code")

    assert exc.value.code == "TASK_ALREADY_CLAIMED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_tasks_events_inbox.py::test_create_list_show_and_claim_task tests/test_tasks_events_inbox.py::test_claim_task_is_atomic -v
```

Expected: FAIL because task methods do not exist.

- [ ] **Step 3: Add task helpers and service methods**

Append these methods inside `HubService` in `src/agenthub/service.py`:

```python
    def _next_public_id(self, table: str, prefix: str) -> str:
        with connect(self.paths) as conn:
            row = conn.execute(f"select seq from sqlite_sequence where name = ?", (table,)).fetchone()
            next_number = 1 if row is None else int(row["seq"]) + 1
        return f"{prefix}{next_number:06d}"

    def create_task(self, title: str, intent: str, priority: str, refs: list[dict[str, str]]) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            cursor = conn.execute(
                """
                insert into tasks (title, intent, status, priority, created_at, updated_at, refs_json)
                values (?, ?, 'open', ?, ?, ?, ?)
                """,
                (title, intent, priority, now, now, dumps_json(refs)),
            )
            public_id = f"T{cursor.lastrowid:06d}"
            conn.execute("update tasks set id = ? where pk = ?", (public_id, cursor.lastrowid))
        return self.show_task(public_id, brief=False)

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "select id, title, intent, status, owner_agent_id, priority, created_at, updated_at, refs_json, summary from tasks"
        params: tuple[Any, ...] = ()
        if status:
            query += " where status = ?"
            params = (status,)
        query += " order by pk"
        with connect(self.paths) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def show_task(self, task_id: str, brief: bool) -> dict[str, Any]:
        with connect(self.paths) as conn:
            row = conn.execute(
                "select id, title, intent, status, owner_agent_id, priority, created_at, updated_at, closed_at, refs_json, summary from tasks where id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise HubError("TASK_NOT_FOUND", f"Task {task_id} was not found", "Run hub task list.")
            payload = dict(row)
            if brief:
                events = conn.execute(
                    "select id, task_id, type, by_agent_id, body, refs_json, cursor, created_at from events where task_id = ? order by cursor desc limit 5",
                    (task_id,),
                ).fetchall()
                payload["recent_events"] = [dict(event) for event in reversed(events)]
        return payload

    def claim_task(self, task_id: str, agent_id: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            agent = conn.execute("select id from agents where id = ?", (agent_id,)).fetchone()
            if agent is None:
                raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Register the agent first.")
            result = conn.execute(
                """
                update tasks
                set status = 'claimed', owner_agent_id = ?, updated_at = ?
                where id = ? and status = 'open' and owner_agent_id is null
                """,
                (agent_id, now, task_id),
            )
            if result.rowcount == 0:
                existing = conn.execute("select owner_agent_id from tasks where id = ?", (task_id,)).fetchone()
                if existing is None:
                    raise HubError("TASK_NOT_FOUND", f"Task {task_id} was not found", "Run hub task list.")
                raise HubError("TASK_ALREADY_CLAIMED", f"Task {task_id} is already claimed by {existing['owner_agent_id']}", "Use hub handoff or task reassign if ownership should change.")
            self._insert_event(conn, task_id, "claim", agent_id, f"claimed by {agent_id}", [])
        return self.show_task(task_id, brief=False)

    def _insert_event(
        self,
        conn,
        task_id: str | None,
        event_type: str,
        by_agent_id: str,
        body: str,
        refs: list[dict[str, str]],
    ) -> dict[str, Any]:
        cursor_row = conn.execute("select coalesce(max(cursor), 0) + 1 as next_cursor from events").fetchone()
        next_cursor = int(cursor_row["next_cursor"])
        row = conn.execute(
            """
            insert into events (task_id, type, by_agent_id, body, refs_json, cursor, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, event_type, by_agent_id, body, dumps_json(refs), next_cursor, utc_now()),
        )
        public_id = f"E{row.lastrowid:06d}"
        conn.execute("update events set id = ? where pk = ?", (public_id, row.lastrowid))
        return {
            "id": public_id,
            "task_id": task_id,
            "type": event_type,
            "by_agent_id": by_agent_id,
            "body": body,
            "refs_json": dumps_json(refs),
            "cursor": next_cursor,
        }
```

- [ ] **Step 4: Run task service tests**

Run:

```bash
pytest tests/test_tasks_events_inbox.py::test_create_list_show_and_claim_task tests/test_tasks_events_inbox.py::test_claim_task_is_atomic -v
```

Expected: PASS.

- [ ] **Step 5: Wire task CLI commands**

Replace the existing task command in `src/agenthub/cli.py` and add the missing task commands:

```python
@task_app.command("create")
def task_create(
    title: str = typer.Option(..., "--title"),
    intent: str = typer.Option(..., "--intent"),
    priority: str = typer.Option("normal", "--priority"),
    ref: list[str] = typer.Option([], "--ref"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
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
    rows = service_for(workspace).list_tasks(status=status)
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
    try:
        echo_json(service_for(workspace).claim_task(task_id, agent))
    except HubError as exc:
        handle_error(exc)
```

- [ ] **Step 6: Add CLI task flow test**

Append to `tests/test_cli_jsonl.py`:

```python

def test_task_create_claim_and_show_cli(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0

    created = runner.invoke([
        "task", "create",
        "--title", "Wire CLI",
        "--intent", "Build first path",
        "--workspace", str(hub_home),
    ])
    assert created.exit_code == 0
    task = json.loads(created.stdout)
    assert task["id"] == "T000001"

    claimed = runner.invoke(["task", "claim", "T000001", "--agent", "codex", "--workspace", str(hub_home)])
    assert claimed.exit_code == 0
    assert json.loads(claimed.stdout)["owner_agent_id"] == "codex"

    shown = runner.invoke(["task", "show", "T000001", "--brief", "--workspace", str(hub_home)])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["recent_events"][0]["type"] == "claim"
```

- [ ] **Step 7: Run task and CLI tests**

Run:

```bash
pytest tests/test_tasks_events_inbox.py tests/test_cli_jsonl.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit task work**

```bash
git add src/agenthub/service.py src/agenthub/cli.py tests/test_tasks_events_inbox.py tests/test_cli_jsonl.py
git commit -m "feat: add task lifecycle commands"
```

---

### Task 6: Event Push and Inbox Pull

**Files:**
- Modify: `src/agenthub/service.py`
- Modify: `src/agenthub/cli.py`
- Modify: `tests/test_tasks_events_inbox.py`
- Modify: `tests/test_cli_jsonl.py`

- [ ] **Step 1: Add failing event and inbox tests**

Append to `tests/test_tasks_events_inbox.py`:

```python

def test_push_event_and_pull_inbox_advances_cursor(service):
    task = service.create_task("Events", "Test inbox", "normal", [])
    event = service.push_event(task["id"], "codex", "status", "schema done", [])

    first_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=False)
    second_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=False)

    assert event["id"] == "E000001"
    assert first_pull["events"][0]["body"] == "schema done"
    assert first_pull["last_cursor"] == 1
    assert second_pull["events"] == []


def test_pull_inbox_peek_does_not_advance_cursor(service):
    task = service.create_task("Peek", "Test peek", "normal", [])
    service.push_event(task["id"], "codex", "status", "peekable", [])

    first_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=True)
    second_pull = service.pull_inbox("claude-code", limit=10, since=None, peek=False)

    assert first_pull["events"][0]["body"] == "peekable"
    assert second_pull["events"][0]["body"] == "peekable"


def test_event_body_budget_is_enforced(service):
    task = service.create_task("Budget", "Test body budget", "normal", [])
    long_body = "x" * 281

    with pytest.raises(HubError) as exc:
        service.push_event(task["id"], "codex", "status", long_body, [])

    assert exc.value.code == "BODY_TOO_LARGE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_tasks_events_inbox.py::test_push_event_and_pull_inbox_advances_cursor tests/test_tasks_events_inbox.py::test_pull_inbox_peek_does_not_advance_cursor tests/test_tasks_events_inbox.py::test_event_body_budget_is_enforced -v
```

Expected: FAIL because event and inbox methods do not exist.

- [ ] **Step 3: Implement event and inbox service methods**

Update imports in `src/agenthub/service.py`:

```python
from agenthub.models import AGENT_STATUSES, EVENT_TYPES, dumps_json, utc_now
from agenthub.profiles import get_profile
```

Append methods inside `HubService`:

```python
    def push_event(
        self,
        task_id: str | None,
        agent_id: str,
        event_type: str,
        body: str,
        refs: list[dict[str, str]],
    ) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise HubError("INVALID_EVENT_TYPE", f"Event type {event_type} is invalid", f"Use one of {sorted(EVENT_TYPES)}.")
        agent = self.show_agent(agent_id)
        profile = get_profile(agent["profile_name"])
        if len(body) > profile.event_body_budget_chars:
            raise HubError("BODY_TOO_LARGE", f"Event body is {len(body)} characters", f"Keep body under {profile.event_body_budget_chars} characters and move details into refs.")
        with connect(self.paths) as conn:
            if task_id is not None:
                task = conn.execute("select id from tasks where id = ?", (task_id,)).fetchone()
                if task is None:
                    raise HubError("TASK_NOT_FOUND", f"Task {task_id} was not found", "Run hub task list.")
            event = self._insert_event(conn, task_id, event_type, agent_id, body, refs)
        return event

    def pull_inbox(
        self,
        agent_id: str,
        limit: int,
        since: int | None,
        peek: bool,
    ) -> dict[str, Any]:
        self.show_agent(agent_id)
        with connect(self.paths) as conn:
            if since is None:
                offset = conn.execute("select last_cursor from inbox_offsets where agent_id = ?", (agent_id,)).fetchone()
                start_cursor = 0 if offset is None else int(offset["last_cursor"])
            else:
                start_cursor = since
            rows = conn.execute(
                """
                select id, task_id, type, by_agent_id, body, refs_json, cursor, created_at
                from events
                where cursor > ? and by_agent_id != ?
                order by cursor
                limit ?
                """,
                (start_cursor, agent_id, limit),
            ).fetchall()
            events = [dict(row) for row in rows]
            last_cursor = events[-1]["cursor"] if events else start_cursor
            if events and not peek and since is None:
                conn.execute(
                    "insert into inbox_offsets (agent_id, last_cursor) values (?, ?) on conflict(agent_id) do update set last_cursor = excluded.last_cursor",
                    (agent_id, last_cursor),
                )
        return {"agent_id": agent_id, "last_cursor": last_cursor, "events": events}
```

- [ ] **Step 4: Run event and inbox service tests**

Run:

```bash
pytest tests/test_tasks_events_inbox.py -v
```

Expected: PASS.

- [ ] **Step 5: Wire event and inbox CLI commands**

Replace `event_push` and `inbox_pull` in `src/agenthub/cli.py`:

```python
@event_app.command("push")
def event_push(
    task: str | None = typer.Option(None, "--task"),
    agent: str = typer.Option(..., "--agent"),
    type: str = typer.Option(..., "--type"),
    body: str = typer.Option(..., "--body"),
    ref: list[str] = typer.Option([], "--ref"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
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
    try:
        payload = service_for(workspace).pull_inbox(agent, limit, since, peek)
    except HubError as exc:
        handle_error(exc)
        return
    if format == "jsonl":
        echo_jsonl(payload["events"])
    else:
        echo_json(payload)
```

- [ ] **Step 6: Add CLI event/inbox test**

Append to `tests/test_cli_jsonl.py`:

```python

def test_event_push_and_inbox_pull_cli(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "claude-code", "--profile", "claude-code", "--workspace", str(hub_home)]).exit_code == 0
    created = runner.invoke([
        "task", "create", "--title", "Events", "--intent", "Test", "--workspace", str(hub_home)
    ])
    task_id = json.loads(created.stdout)["id"]

    pushed = runner.invoke([
        "event", "push", "--task", task_id, "--agent", "codex", "--type", "status", "--body", "schema done", "--workspace", str(hub_home)
    ])
    assert pushed.exit_code == 0

    pulled = runner.invoke([
        "inbox", "pull", "--agent", "claude-code", "--workspace", str(hub_home)
    ])
    assert pulled.exit_code == 0
    rows = [json.loads(line) for line in pulled.stdout.splitlines()]
    assert rows[0]["body"] == "schema done"
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/test_tasks_events_inbox.py tests/test_cli_jsonl.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit event and inbox work**

```bash
git add src/agenthub/service.py src/agenthub/cli.py tests/test_tasks_events_inbox.py tests/test_cli_jsonl.py
git commit -m "feat: add event and inbox flow"
```

---

### Task 7: Watch Command

**Files:**
- Modify: `src/agenthub/cli.py`
- Modify: `tests/test_cli_jsonl.py`

- [ ] **Step 1: Add failing watch CLI test**

Append to `tests/test_cli_jsonl.py`:

```python

def test_watch_cli_can_run_once_for_tests(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "claude-code", "--profile", "claude-code", "--workspace", str(hub_home)]).exit_code == 0
    created = runner.invoke([
        "task", "create", "--title", "Watch", "--intent", "Test", "--workspace", str(hub_home)
    ])
    task_id = json.loads(created.stdout)["id"]
    assert runner.invoke([
        "event", "push", "--task", task_id, "--agent", "codex", "--type", "status", "--body", "watch me", "--workspace", str(hub_home)
    ]).exit_code == 0

    watched = runner.invoke([
        "watch", "--agent", "claude-code", "--once", "--workspace", str(hub_home)
    ])

    assert watched.exit_code == 0
    rows = [json.loads(line) for line in watched.stdout.splitlines()]
    assert rows[0]["body"] == "watch me"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_cli_jsonl.py::test_watch_cli_can_run_once_for_tests -v
```

Expected: FAIL because `watch` ignores options and does not pull events.

- [ ] **Step 3: Implement testable watch command**

Replace `watch` in `src/agenthub/cli.py` and add `time` import:

```python
import time
```

```python
@app.command()
def watch(
    agent: str = typer.Option(..., "--agent"),
    interval: str = typer.Option("1s", "--interval"),
    format: str = typer.Option("jsonl", "--format"),
    peek: bool = typer.Option(False, "--peek"),
    once: bool = typer.Option(False, "--once", help="Run one polling iteration, useful for tests."),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Watch inbox events as JSONL."""
    seconds = _parse_interval_seconds(interval)
    while True:
        try:
            payload = service_for(workspace).pull_inbox(agent, limit=100, since=None, peek=peek)
        except HubError as exc:
            handle_error(exc)
            return
        if format == "jsonl":
            echo_jsonl(payload["events"])
        else:
            echo_json(payload)
        if once:
            return
        time.sleep(seconds)


def _parse_interval_seconds(value: str) -> float:
    if value.endswith("ms"):
        return max(float(value[:-2]) / 1000, 0.05)
    if value.endswith("s"):
        return max(float(value[:-1]), 0.05)
    return max(float(value), 0.05)
```

- [ ] **Step 4: Run watch test**

Run:

```bash
pytest tests/test_cli_jsonl.py::test_watch_cli_can_run_once_for_tests -v
```

Expected: PASS.

- [ ] **Step 5: Run full CLI tests**

Run:

```bash
pytest tests/test_cli_jsonl.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit watch command**

```bash
git add src/agenthub/cli.py tests/test_cli_jsonl.py
git commit -m "feat: add watch command"
```

---

### Task 8: Read-Only Dashboard Service Queries

**Files:**
- Modify: `src/agenthub/service.py`
- Create: `tests/test_ui.py`

- [ ] **Step 1: Write failing dashboard service test**

Create `tests/test_ui.py`:

```python
from __future__ import annotations

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


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

    assert snapshot["radar"]["agents_total"] == 2
    assert snapshot["radar"]["agents_active"] == 1
    assert snapshot["radar"]["tasks_blocked"] == 0
    assert snapshot["tasks"][0]["id"] == "T000001"
    assert snapshot["timeline"][-1]["body"] == "visible"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_ui.py::test_dashboard_snapshot_contains_radar_tasks_and_timeline -v
```

Expected: FAIL because `dashboard_snapshot` does not exist.

- [ ] **Step 3: Implement dashboard snapshot**

Append to `HubService` in `src/agenthub/service.py`:

```python
    def dashboard_snapshot(self) -> dict[str, Any]:
        with connect(self.paths) as conn:
            agents = [dict(row) for row in conn.execute(
                "select id, display_name, profile_name, status, last_seen_at from agents order by id"
            ).fetchall()]
            tasks = [dict(row) for row in conn.execute(
                "select id, title, intent, status, owner_agent_id, priority, created_at, updated_at, refs_json from tasks order by pk desc limit 100"
            ).fetchall()]
            timeline = [dict(row) for row in conn.execute(
                "select id, task_id, type, by_agent_id, body, refs_json, cursor, created_at from events order by cursor desc limit 100"
            ).fetchall()]
            handoffs_pending = conn.execute("select count(*) from handoffs where status = 'pending'").fetchone()[0]
        return {
            "radar": {
                "agents_total": len(agents),
                "agents_active": sum(1 for agent in agents if agent["status"] == "active"),
                "agents_paused": sum(1 for agent in agents if agent["status"] == "paused"),
                "tasks_blocked": sum(1 for task in tasks if task["status"] == "blocked"),
                "handoffs_pending": handoffs_pending,
                "events_recent": len(timeline),
            },
            "agents": agents,
            "tasks": tasks,
            "timeline": list(reversed(timeline)),
        }
```

- [ ] **Step 4: Run dashboard service test**

Run:

```bash
pytest tests/test_ui.py::test_dashboard_snapshot_contains_radar_tasks_and_timeline -v
```

Expected: PASS.

- [ ] **Step 5: Run service tests**

Run:

```bash
pytest tests/test_tasks_events_inbox.py tests/test_ui.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit dashboard query**

```bash
git add src/agenthub/service.py tests/test_ui.py
git commit -m "feat: add dashboard snapshot query"
```

---

### Task 9: FastAPI Monitor UI

**Files:**
- Create: `src/agenthub/ui.py`
- Create: `src/agenthub/templates/base.html`
- Create: `src/agenthub/templates/index.html`
- Create: `src/agenthub/static/app.css`
- Modify: `src/agenthub/cli.py`
- Modify: `tests/test_ui.py`

- [ ] **Step 1: Add failing UI app tests**

Append to `tests/test_ui.py`:

```python
from fastapi.testclient import TestClient

from agenthub.ui import create_app


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
```

- [ ] **Step 2: Run UI test to verify it fails**

Run:

```bash
pytest tests/test_ui.py::test_ui_dashboard_api_and_page -v
```

Expected: FAIL because `agenthub.ui` does not exist.

- [ ] **Step 3: Implement FastAPI app factory**

Create `src/agenthub/ui.py`:

```python
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

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
    templates = Jinja2Templates(directory=str(package_files / "templates"))
    app.mount("/static", StaticFiles(directory=str(package_files / "static")), name="static")

    @app.get("/api/dashboard")
    def dashboard_api():
        return HubService(paths).dashboard_snapshot()

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        snapshot = HubService(paths).dashboard_snapshot()
        return templates.TemplateResponse("index.html", {"request": request, "snapshot": snapshot})

    return app


def run_ui(paths: HubPaths, host: str, port: int) -> None:
    uvicorn.run(create_app(paths), host=host, port=port)
```

- [ ] **Step 4: Add templates**

Create `src/agenthub/templates/base.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AgentHub Monitor</title>
    <link rel="stylesheet" href="/static/app.css">
  </head>
  <body>
    <main class="shell">
      {% block content %}{% endblock %}
    </main>
  </body>
</html>
```

Create `src/agenthub/templates/index.html`:

```html
{% extends "base.html" %}
{% block content %}
<section class="hero">
  <p class="eyebrow">local control tower</p>
  <h1>AgentHub Radar</h1>
  <p class="lede">A compact view of local agent coordination, task ownership, and event flow.</p>
</section>

<section class="radar-grid">
  <article class="metric"><span>Total Agents</span><strong>{{ snapshot.radar.agents_total }}</strong></article>
  <article class="metric"><span>Active</span><strong>{{ snapshot.radar.agents_active }}</strong></article>
  <article class="metric warning"><span>Blocked Tasks</span><strong>{{ snapshot.radar.tasks_blocked }}</strong></article>
  <article class="metric"><span>Recent Events</span><strong>{{ snapshot.radar.events_recent }}</strong></article>
</section>

<section class="panel-grid">
  <article class="panel">
    <h2>Tasks</h2>
    <div class="table">
      {% for task in snapshot.tasks %}
      <div class="row">
        <span class="mono">{{ task.id }}</span>
        <span>{{ task.title }}</span>
        <span class="pill">{{ task.status }}</span>
        <span>{{ task.owner_agent_id or "unowned" }}</span>
      </div>
      {% endfor %}
    </div>
  </article>

  <article class="panel">
    <h2>Timeline</h2>
    <div class="timeline">
      {% for event in snapshot.timeline %}
      <div class="event">
        <span class="mono">{{ event.id }}</span>
        <strong>{{ event.type }}</strong>
        <span>{{ event.by_agent_id }}</span>
        <p>{{ event.body }}</p>
      </div>
      {% endfor %}
    </div>
  </article>
</section>
{% endblock %}
```

- [ ] **Step 5: Add UI styling**

Create `src/agenthub/static/app.css`:

```css
:root {
  --graphite: #151716;
  --panel: #202421;
  --panel-strong: #2b302c;
  --fog: #eef1e8;
  --muted: #9fa89b;
  --amber: #ffb000;
  --signal: #2ee6a6;
  --line: rgba(238, 241, 232, 0.12);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  color: var(--fog);
  background:
    radial-gradient(circle at top left, rgba(46, 230, 166, 0.16), transparent 32rem),
    linear-gradient(135deg, #111311, var(--graphite));
  font-family: "Avenir Next", "IBM Plex Sans", sans-serif;
}

.shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 48px 0;
}

.hero {
  border-bottom: 1px solid var(--line);
  margin-bottom: 24px;
  padding-bottom: 24px;
}

.eyebrow {
  color: var(--signal);
  font-family: "IBM Plex Mono", monospace;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

h1, h2, p { margin-top: 0; }
h1 { font-size: clamp(2.5rem, 7vw, 5.5rem); line-height: 0.9; margin-bottom: 16px; }
h2 { font-size: 1rem; letter-spacing: 0.08em; text-transform: uppercase; }
.lede { color: var(--muted); max-width: 720px; }

.radar-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.metric, .panel {
  background: linear-gradient(180deg, var(--panel-strong), var(--panel));
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.24);
}

.metric { padding: 18px; }
.metric span { color: var(--muted); display: block; font-size: 0.78rem; text-transform: uppercase; }
.metric strong { color: var(--signal); display: block; font-size: 2.5rem; margin-top: 8px; }
.metric.warning strong { color: var(--amber); }

.panel-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.panel { min-height: 360px; padding: 18px; }
.row, .event {
  border-top: 1px solid var(--line);
  display: grid;
  gap: 12px;
  padding: 12px 0;
}
.row { grid-template-columns: 90px 1fr 90px 120px; }
.event { grid-template-columns: 90px 90px 120px 1fr; }
.event p { margin: 0; color: var(--fog); }

.mono { color: var(--muted); font-family: "IBM Plex Mono", monospace; }
.pill { color: var(--graphite); background: var(--signal); border-radius: 999px; padding: 3px 8px; text-align: center; }

@media (max-width: 820px) {
  .radar-grid, .panel-grid { grid-template-columns: 1fr; }
  .row, .event { grid-template-columns: 1fr; }
}
```

- [ ] **Step 6: Wire `hub ui`**

Modify `src/agenthub/cli.py` imports:

```python
from agenthub.ui import run_ui
```

Replace `ui` command:

```python
@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    workspace: Path = typer.Option(Path("."), "--workspace"),
) -> None:
    """Start the local monitor UI."""
    run_ui(HubPaths.from_workspace(workspace), host=host, port=port)
```

- [ ] **Step 7: Run UI tests**

Run:

```bash
pytest tests/test_ui.py -v
```

Expected: PASS.

- [ ] **Step 8: Run full test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 9: Commit UI work**

```bash
git add src/agenthub/ui.py src/agenthub/templates src/agenthub/static src/agenthub/cli.py tests/test_ui.py
git commit -m "feat: add read-only monitor UI"
```

---

### Task 10: Load Smoke Test and README Polish

**Files:**
- Create: `tests/test_load_smoke.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing load smoke test if performance is pathological**

Create `tests/test_load_smoke.py`:

```python
from __future__ import annotations

import time

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.service import HubService


def test_insert_1000_short_events_and_query_timeline(hub_home):
    paths = HubPaths.from_workspace(hub_home)
    init_db(paths)
    service = HubService(paths)
    service.register_agent("codex", "codex")
    service.register_agent("claude-code", "claude-code")
    task = service.create_task("Load", "Smoke test events", "normal", [])

    start = time.monotonic()
    for index in range(1000):
        service.push_event(task["id"], "codex", "status", f"event {index}", [])
    snapshot = service.dashboard_snapshot()
    elapsed = time.monotonic() - start

    assert len(snapshot["timeline"]) == 100
    assert snapshot["timeline"][-1]["body"] == "event 999"
    assert elapsed < 10
```

- [ ] **Step 2: Run load smoke test**

Run:

```bash
pytest tests/test_load_smoke.py -v
```

Expected: PASS in under 10 seconds on a normal local machine. If it fails because inserts are too slow, add a batched event insertion helper only for tests after discussing scope; do not silently weaken the assertion.

- [ ] **Step 3: Update README quick start**

Replace `README.md` with:

````markdown
# AgentHub

AgentHub is a local-first coordination hub for multiple agents. It uses short structured events, task cards, artifact references, and a local monitor UI.

## Install for Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```bash
hub init
hub agent register codex --profile codex
hub agent register claude-code --profile claude-code
hub agent heartbeat codex --status active
hub brief --agent codex
hub task create --title "Wire CLI" --intent "Build the first CLI path" --priority normal
hub task claim T000001 --agent codex
hub event push --task T000001 --agent codex --type status --body "started"
hub inbox pull --agent claude-code --format jsonl
hub ui
```

Open the monitor at `http://127.0.0.1:8765`.

## Low-Token Rules

- Keep event bodies short.
- Put large content in `--ref` paths instead of message bodies.
- Use `hub task show T000001 --brief` when an agent only needs current state.
- Use `hub inbox pull --agent <id> --limit 10 --format jsonl` for routine coordination.

## First-Class Profiles

- `codex`
- `claude-code`
- `openclaw`
- `hermes`
````

- [ ] **Step 4: Run full tests**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 5: Commit smoke test and docs**

```bash
git add README.md tests/test_load_smoke.py
git commit -m "test: add AgentHub load smoke coverage"
```

---

### Task 11: Final Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run full test suite**

Run:

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run a manual CLI flow**

Run:

```bash
rm -rf /tmp/agenthub-manual
mkdir -p /tmp/agenthub-manual
hub init --workspace /tmp/agenthub-manual
hub agent register codex --profile codex --workspace /tmp/agenthub-manual
hub agent register claude-code --profile claude-code --workspace /tmp/agenthub-manual
hub agent heartbeat codex --status active --workspace /tmp/agenthub-manual
hub task create --title "Manual smoke" --intent "Verify CLI" --workspace /tmp/agenthub-manual
hub task claim T000001 --agent codex --workspace /tmp/agenthub-manual
hub event push --task T000001 --agent codex --type status --body "manual ok" --workspace /tmp/agenthub-manual
hub inbox pull --agent claude-code --workspace /tmp/agenthub-manual
```

Expected final output includes one JSON line with `"body":"manual ok"`.

- [ ] **Step 3: Verify UI app imports**

Run:

```bash
python - <<'PY'
from agenthub.config import HubPaths
from agenthub.ui import create_app
app = create_app(HubPaths.from_workspace('/tmp/agenthub-manual'))
print(app.title)
PY
```

Expected output:

```text
AgentHub Monitor
```

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: clean worktree.

- [ ] **Step 5: Commit any final fixes**

If final verification required changes, commit them:

```bash
git add <changed-files>
git commit -m "fix: complete AgentHub MVP verification"
```

If no changes were required, do not create an empty commit.

---

## Plan Self-Review

### Spec Coverage

This plan covers the first implementation slice from the design spec:

- SQLite source of truth in `.agenthub/hub.db`.
- Python package and `hub` console script.
- `hub init`.
- Default profiles for `codex`, `claude-code`, `openclaw`, and `hermes`.
- `hub brief` and `hub doctor` for low-token agent onboarding.
- Agent registry discovery through `register`, `heartbeat`, `list`, and `show`.
- Task creation, listing, showing, and atomic claim.
- Short structured event push with body budget validation.
- Cursor-based inbox pull with consuming and `--peek` behavior.
- `watch` as a polling wrapper over inbox pull.
- Read-only monitor UI with Radar, Tasks, and Timeline.
- Load smoke coverage for `1,000` short events.

### Intentionally Deferred

These spec items are post-MVP and should get separate implementation plans:

- `hub task block`, `hub task close`, and task reassignment.
- `hub handoff` and `hub handoff accept`.
- `hub compact` and archival modes.
- UI management actions such as pause, resume, reassign, close, and compact preview.
- Native OpenClaw and Hermes plugins.
- Richer stale-agent detection based on heartbeat age.

### Placeholder Scan

The plan must contain no unresolved marker text or vague testing steps. Every code-changing step includes concrete file content or exact code blocks, and every verification step includes an exact command and expected result.
