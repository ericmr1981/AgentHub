from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HubError(Exception):
    code: str
    message: str
    hint: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.hint:
            payload["error"]["hint"] = self.hint
        return payload
