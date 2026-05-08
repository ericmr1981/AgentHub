from __future__ import annotations

import json

from agenthub.config import HubPaths
from agenthub.db import init_db
from agenthub.errors import HubError
from agenthub.profiles import DEFAULT_PROFILES, build_brief
from agenthub.service import HubService


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
