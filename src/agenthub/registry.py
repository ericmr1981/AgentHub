from __future__ import annotations

from typing import Any

from agenthub.db import connect
from agenthub.models import dumps_json, loads_json

DEFAULT_PROFILE = "codex"

CARD_FIELDS = {"description", "skills", "url"}


class AgentRegistry:
    """Stores A2A Agent Cards and manages agent metadata."""

    def __init__(self, service: Any) -> None:
        self._svc = service

    def register(self, agent_id: str, card: dict) -> dict:
        """Register an agent with its A2A Agent Card."""
        self._svc.register_agent(agent_id, DEFAULT_PROFILE)
        # Override display_name with the card's name (the profile gives us
        # a "Codex" display_name, but the card's name is what the caller
        # wants as the A2A agent name).
        card_name = card.get("name", agent_id)
        with connect(self._svc.paths) as conn:
            conn.execute(
                "update agents set display_name = ? where id = ?",
                (card_name, agent_id),
            )
        self._svc.heartbeat_agent(agent_id, "active")
        self._update_metadata(agent_id, card)
        return self.lookup(agent_id)

    def lookup(self, agent_id: str) -> dict:
        """Look up an agent and return its card data."""
        agent = self._svc.show_agent(agent_id)
        return self._build_card(agent)

    def list_all(self) -> list[dict]:
        """List all registered agents with their card data."""
        agents = self._svc.list_agents()
        return [self._build_card(a) for a in agents]

    def _update_metadata(self, agent_id: str, card: dict) -> None:
        """Store card fields in the agent's metadata_json column."""
        with connect(self._svc.paths) as conn:
            row = conn.execute(
                "select metadata_json from agents where id = ?", (agent_id,)
            ).fetchone()
            existing = loads_json(row["metadata_json"] if row else None, {})
            for key in CARD_FIELDS:
                if key in card:
                    existing[key] = card[key]
            conn.execute(
                "update agents set metadata_json = ? where id = ?",
                (dumps_json(existing), agent_id),
            )

    def _build_card(self, agent: dict) -> dict:
        """Build an agent card from a DB row, merging stored metadata."""
        metadata = loads_json(agent.get("metadata_json"), {})

        # Rename display_name -> name in the card output (A2A convention).
        result: dict[str, Any] = {
            "id": agent["id"],
            "name": agent["display_name"],
            "status": agent["status"],
            "last_seen_at": agent["last_seen_at"],
        }
        # Merge stored card fields.
        for key in CARD_FIELDS:
            if key in metadata:
                result[key] = metadata[key]
        return result
