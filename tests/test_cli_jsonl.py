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
