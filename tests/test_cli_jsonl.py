from __future__ import annotations

import json


def test_version_command_outputs_version(runner):
    result = runner.invoke(["version"])

    assert result.exit_code == 0
    assert "AgentHub" in result.stdout


def test_root_help_lists_core_commands(runner):
    result = runner.invoke(["--help"])

    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "agent" in result.stdout
    assert "task" in result.stdout
    assert "event" in result.stdout
    assert "inbox" in result.stdout
    assert "watch" in result.stdout
    assert "ui" in result.stdout


def test_agent_register_and_list_cli(runner, hub_home):
    init_result = runner.invoke(["init", "--workspace", str(hub_home)])
    assert init_result.exit_code == 0

    register_result = runner.invoke([
        "agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)
    ])
    assert register_result.exit_code == 0
    registered = json.loads(register_result.stdout)
    assert registered["id"] == "codex"

    list_result = runner.invoke(["agent", "list", "--workspace", str(hub_home)])
    assert list_result.exit_code == 0
    rows = [json.loads(line) for line in list_result.stdout.splitlines()]
    assert rows[0]["id"] == "codex"


def test_brief_cli_outputs_profile_help(runner):
    result = runner.invoke(["brief", "--agent", "codex"])

    assert result.exit_code == 0
    assert "AgentHub brief for codex" in result.stdout
    assert "hub inbox pull --agent codex" in result.stdout


def test_task_create_claim_and_show_cli(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0

    created = runner.invoke([
        "task", "create",
        "--title", "Wire CLI",
        "--intent", "Build first path",
        "--workspace", str(hub_home),
    ])
    assert created.exit_code == 0
    task = json.loads(created.stdout)
    assert task["id"] == "T000001"

    claimed = runner.invoke(["task", "claim", "T000001", "--agent", "codex", "--workspace", str(hub_home)])
    assert claimed.exit_code == 0
    assert json.loads(claimed.stdout)["owner_agent_id"] == "codex"

    shown = runner.invoke(["task", "show", "T000001", "--brief", "--workspace", str(hub_home)])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["recent_events"][0]["type"] == "claim"


def test_event_push_and_inbox_pull_cli(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "claude-code", "--profile", "claude-code", "--workspace", str(hub_home)]).exit_code == 0
    created = runner.invoke([
        "task", "create", "--title", "Events", "--intent", "Test", "--workspace", str(hub_home)
    ])
    task_id = json.loads(created.stdout)["id"]

    pushed = runner.invoke([
        "event", "push", "--task", task_id, "--agent", "codex", "--type", "status", "--body", "schema done", "--workspace", str(hub_home)
    ])
    assert pushed.exit_code == 0

    pulled = runner.invoke([
        "inbox", "pull", "--agent", "claude-code", "--workspace", str(hub_home)
    ])
    assert pulled.exit_code == 0
    rows = [json.loads(line) for line in pulled.stdout.splitlines()]
    assert rows[0]["body"] == "schema done"


def test_task_block_and_close_cli(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["task", "create", "--title", "Block", "--intent", "Test", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["task", "claim", "T000001", "--agent", "codex", "--workspace", str(hub_home)]).exit_code == 0

    blocked = runner.invoke(["task", "block", "T000001", "--agent", "codex", "--reason", "needs schema", "--workspace", str(hub_home)])
    assert blocked.exit_code == 0
    assert json.loads(blocked.stdout)["status"] == "blocked"

    closed = runner.invoke(["task", "close", "T000001", "--agent", "codex", "--summary", "done", "--workspace", str(hub_home)])
    assert closed.exit_code == 0
    assert json.loads(closed.stdout)["status"] == "done"


def test_watch_cli_can_run_once_for_tests(runner, hub_home):
    assert runner.invoke(["init", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "codex", "--profile", "codex", "--workspace", str(hub_home)]).exit_code == 0
    assert runner.invoke(["agent", "register", "claude-code", "--profile", "claude-code", "--workspace", str(hub_home)]).exit_code == 0
    created = runner.invoke([
        "task", "create", "--title", "Watch", "--intent", "Test", "--workspace", str(hub_home)
    ])
    task_id = json.loads(created.stdout)["id"]
    assert runner.invoke([
        "event", "push", "--task", task_id, "--agent", "codex", "--type", "status", "--body", "watch me", "--workspace", str(hub_home)
    ]).exit_code == 0

    watched = runner.invoke([
        "watch", "--agent", "claude-code", "--once", "--workspace", str(hub_home)
    ])

    assert watched.exit_code == 0
    rows = [json.loads(line) for line in watched.stdout.splitlines()]
    assert rows[0]["body"] == "watch me"
