from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agenthub.cli import app


class HubCliRunner:
    def __init__(self) -> None:
        self._runner = CliRunner()

    def invoke(self, args: list[str]):
        return self._runner.invoke(app, args)


@pytest.fixture()
def runner() -> HubCliRunner:
    return HubCliRunner()


@pytest.fixture()
def hub_home(tmp_path: Path) -> Path:
    return tmp_path / "workspace"
