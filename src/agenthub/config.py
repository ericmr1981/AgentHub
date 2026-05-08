from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HubPaths:
    workspace: Path
    hub_dir: Path
    db_path: Path

    @classmethod
    def from_workspace(cls, workspace: Path | str = ".") -> "HubPaths":
        root = Path(workspace).expanduser().resolve()
        hub_dir = root / ".agenthub"
        return cls(workspace=root, hub_dir=hub_dir, db_path=hub_dir / "hub.db")
