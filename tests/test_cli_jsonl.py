from __future__ import annotations


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


import json


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
