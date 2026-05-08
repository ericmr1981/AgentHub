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
