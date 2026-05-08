# AgentHub

AgentHub is a local-first coordination hub for multiple agents. It uses short structured events, task cards, artifact references, and a local monitor UI.

## MVP Quick Start

```bash
hub init
hub agent register codex --profile codex
hub agent heartbeat codex --status active
hub task create --title "Wire CLI" --intent "Build the first CLI path" --priority normal
hub task list --format jsonl
```
