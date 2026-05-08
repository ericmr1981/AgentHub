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
