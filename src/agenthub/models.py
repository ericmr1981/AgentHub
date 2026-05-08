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
