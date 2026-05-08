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
            f"hub task close T000001 --agent {agent_id} --summary \"done\"",
            f"hub handoff create T000001 --from {agent_id} --to claude-code --reason \"please review\"",
            "",
            "Agent management:",
            f"hub agent pause {agent_id}",
            f"hub agent resume {agent_id}",
            "",
            "Task state commands:",
            f"hub task block T000001 --agent {agent_id} --reason \"blocked\"",
            f"hub task close T000001 --agent {agent_id} --summary \"complete\"",
            "",
            "Data management:",
            "hub compact --older-than 14d --mode summarize",
            "",
            profile.prompt_snippet,
        ]
    )
