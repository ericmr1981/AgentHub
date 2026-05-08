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

    def doctor_agent(self, agent_id: str) -> dict[str, Any]:
        database_ok = self.paths.db_path.exists()
        with connect(self.paths) as conn:
            row = conn.execute(
                "select id, display_name, profile_name, status, last_seen_at, metadata_json from agents where id = ?",
                (agent_id,),
            ).fetchone()
        agent = dict(row) if row else None
        registered = agent is not None
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
