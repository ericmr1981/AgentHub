from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agenthub.config import HubPaths
from agenthub.db import connect
from agenthub.errors import HubError
from agenthub.models import AGENT_STATUSES, EVENT_TYPES, dumps_json, utc_now
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
            self._insert_event(conn, public_id, "note", "system", f"task created: {title}", [])
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
        with connect(self.paths) as conn:
            agent = conn.execute("select id, profile_name from agents where id = ?", (agent_id,)).fetchone()
            if agent is None:
                raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Register the agent first.")
            profile = get_profile(agent["profile_name"])
            if len(body) > profile.event_body_budget_chars:
                raise HubError("BODY_TOO_LARGE", f"Event body is {len(body)} characters", f"Keep body under {profile.event_body_budget_chars} characters and move details into refs.")
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
        show_all: bool = False,
    ) -> dict[str, Any]:
        with connect(self.paths) as conn:
            agent = conn.execute("select id from agents where id = ?", (agent_id,)).fetchone()
            if agent is None:
                raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Register the agent first.")
            if show_all:
                start_cursor = 0
            elif since is None:
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

    def stream_events(self, since: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """Return all events since a cursor, unfiltered. Used by the SSE stream."""
        with connect(self.paths) as conn:
            rows = conn.execute(
                """
                select id, task_id, type, by_agent_id, body, refs_json, cursor, created_at
                from events
                where cursor > ?
                order by cursor
                limit ?
                """,
                (since, limit),
            ).fetchall()
        return [dict(row) for row in rows]

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

    def block_task(self, task_id: str, agent_id: str, reason: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            result = conn.execute(
                "update tasks set status = 'blocked', summary = ?, updated_at = ? where id = ? and status in ('claimed', 'open')",
                (reason, now, task_id),
            )
            if result.rowcount == 0:
                existing = conn.execute("select status from tasks where id = ?", (task_id,)).fetchone()
                if existing is None:
                    raise HubError("TASK_NOT_FOUND", f"Task {task_id} was not found", "Run hub task list.")
                raise HubError("TASK_NOT_CLAIMABLE", f"Task {task_id} is {existing['status']}, can only block claimed or open tasks", "")
            self._insert_event(conn, task_id, "blocked", agent_id, reason, [])
        return self.show_task(task_id, brief=False)

    def close_task(self, task_id: str, agent_id: str, summary: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            result = conn.execute(
                "update tasks set status = 'done', summary = ?, closed_at = ?, updated_at = ? where id = ? and status != 'done' and status != 'archived'",
                (summary, now, now, task_id),
            )
            if result.rowcount == 0:
                existing = conn.execute("select status from tasks where id = ?", (task_id,)).fetchone()
                if existing is None:
                    raise HubError("TASK_NOT_FOUND", f"Task {task_id} was not found", "Run hub task list.")
                raise HubError("TASK_ALREADY_CLOSED", f"Task {task_id} is already {existing['status']}", "")
            self._insert_event(conn, task_id, "note", agent_id, f"completed: {summary}", [])
        return self.show_task(task_id, brief=False)

    def reassign_task(self, task_id: str, new_agent_id: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            agent = conn.execute("select id from agents where id = ?", (new_agent_id,)).fetchone()
            if agent is None:
                raise HubError("AGENT_NOT_FOUND", f"Agent {new_agent_id} was not found", "Register the agent first.")
            result = conn.execute(
                "update tasks set owner_agent_id = ?, updated_at = ? where id = ? and status in ('claimed', 'blocked')",
                (new_agent_id, now, task_id),
            )
            if result.rowcount == 0:
                existing = conn.execute("select status from tasks where id = ?", (task_id,)).fetchone()
                if existing is None:
                    raise HubError("TASK_NOT_FOUND", f"Task {task_id} was not found", "Run hub task list.")
                raise HubError("TASK_NOT_REASSIGNABLE", f"Task {task_id} is {existing['status']}, can only reassign claimed or blocked tasks", "")
            self._insert_event(conn, task_id, "handoff", new_agent_id, f"reassigned to {new_agent_id}", [])
        return self.show_task(task_id, brief=False)

    def create_handoff(self, task_id: str, from_agent_id: str, to_agent_id: str, reason: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            cursor = conn.execute(
                "insert into handoffs (task_id, from_agent_id, to_agent_id, reason, status, created_at) values (?, ?, ?, ?, 'pending', ?)",
                (task_id, from_agent_id, to_agent_id, reason, now),
            )
            public_id = f"H{cursor.lastrowid:06d}"
            conn.execute("update handoffs set id = ? where pk = ?", (public_id, cursor.lastrowid))
            self._insert_event(conn, task_id, "handoff", from_agent_id, f"handoff to {to_agent_id}: {reason}", [])
        return self.show_handoff(public_id)

    def accept_handoff(self, handoff_id: str, agent_id: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            result = conn.execute(
                "update handoffs set status = 'accepted', accepted_at = ? where id = ? and status = 'pending' and to_agent_id = ?",
                (now, handoff_id, agent_id),
            )
            if result.rowcount == 0:
                existing = conn.execute("select status, to_agent_id from handoffs where id = ?", (handoff_id,)).fetchone()
                if existing is None:
                    raise HubError("HANDOFF_NOT_FOUND", f"Handoff {handoff_id} was not found", "Run hub handoff list.")
                if existing["to_agent_id"] != agent_id:
                    raise HubError("HANDOFF_NOT_FOR_YOU", f"Handoff {handoff_id} is addressed to {existing['to_agent_id']}", "")
                raise HubError("HANDOFF_NOT_PENDING", f"Handoff {handoff_id} is already {existing['status']}", "")
            handoff_row = conn.execute("select task_id from handoffs where pk = (select pk from handoffs where id = ?)", (handoff_id,)).fetchone()
            conn.execute(
                "update tasks set owner_agent_id = ?, updated_at = ? where id = ? and status in ('claimed', 'blocked')",
                (agent_id, now, handoff_row["task_id"]),
            )
            self._insert_event(conn, handoff_row["task_id"], "handoff", agent_id, f"accepted handoff {handoff_id}", [])
        return self.show_handoff(handoff_id)

    def list_handoffs(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "select id, task_id, from_agent_id, to_agent_id, reason, status, created_at, accepted_at from handoffs"
        params: tuple[Any, ...] = ()
        if status:
            query += " where status = ?"
            params = (status,)
        query += " order by pk"
        with connect(self.paths) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def show_handoff(self, handoff_id: str) -> dict[str, Any]:
        with connect(self.paths) as conn:
            row = conn.execute(
                "select id, task_id, from_agent_id, to_agent_id, reason, status, created_at, accepted_at from handoffs where id = ?",
                (handoff_id,),
            ).fetchone()
        if row is None:
            raise HubError("HANDOFF_NOT_FOUND", f"Handoff {handoff_id} was not found", "Run hub handoff list.")
        return dict(row)

    def pause_agent(self, agent_id: str) -> dict[str, Any]:
        with connect(self.paths) as conn:
            result = conn.execute(
                "update agents set status = 'paused' where id = ?",
                (agent_id,),
            )
            if result.rowcount == 0:
                raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Run hub agent list.")
        return self.show_agent(agent_id)

    def resume_agent(self, agent_id: str) -> dict[str, Any]:
        now = utc_now()
        with connect(self.paths) as conn:
            result = conn.execute(
                "update agents set status = 'active', last_seen_at = ? where id = ?",
                (now, agent_id),
            )
            if result.rowcount == 0:
                raise HubError("AGENT_NOT_FOUND", f"Agent {agent_id} was not found", "Run hub agent list.")
        return self.show_agent(agent_id)

    def compact_events(self, days: int, mode: str) -> dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with connect(self.paths) as conn:
            rows = conn.execute(
                "select id, task_id, type, by_agent_id, body, cursor, created_at from events where created_at < ? order by cursor",
                (cutoff,),
            ).fetchall()
            events = [dict(row) for row in rows]
            if not events:
                return {"events_compacted": 0, "summary": None, "mode": mode}

            start_cursor = events[0]["cursor"]
            end_cursor = events[-1]["cursor"]

            if mode == "summarize":
                agent_bodies: dict[str, int] = {}
                for event in events:
                    agent_bodies[event["by_agent_id"]] = agent_bodies.get(event["by_agent_id"], 0) + 1
                parts = [f"{aid} ({count} events)" for aid, count in sorted(agent_bodies.items())]
                summary = f"Compacted {len(events)} events: {', '.join(parts)}"
            else:
                summary = f"Archived {len(events)} events"

            conn.execute(
                "insert into compactions (scope, summary, source_event_start, source_event_end, created_at) "
                "values ('compact', ?, ?, ?, ?)",
                (summary, start_cursor, end_cursor, utc_now()),
            )
            conn.execute("delete from events where cursor between ? and ?", (start_cursor, end_cursor))
        return {"events_compacted": len(events), "summary": summary, "mode": mode}

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
        stale = False
        if agent and agent["last_seen_at"]:
            from datetime import datetime, timezone
            from agenthub.models import STALE_HEARTBEAT_SECONDS
            try:
                last_seen = datetime.fromisoformat(agent["last_seen_at"])
                elapsed = (datetime.now(timezone.utc) - last_seen).total_seconds()
                stale = elapsed > STALE_HEARTBEAT_SECONDS
            except (ValueError, TypeError):
                stale = True
        return {
            "ok": database_ok and registered and profile_ok and heartbeat_ok,
            "agent": agent,
            "checks": {
                "database": database_ok,
                "registered": registered,
                "profile": profile_ok,
                "heartbeat": heartbeat_ok,
                "stale": stale,
            },
        }
