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
    conn = sqlite3.connect(str(paths.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode = wal")
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
    with connect(paths) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            insert or ignore into agents (id, display_name, profile_name, status, last_seen_at, metadata_json)
            values ('system', 'System', 'codex', 'idle', datetime('now'), '{}')
            """
        )
