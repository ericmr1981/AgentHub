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
