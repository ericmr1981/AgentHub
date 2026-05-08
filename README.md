# AgentHub

AgentHub is a local-first coordination hub for multiple agents. It uses short structured events, task cards, artifact references, and a local monitor UI.

## Install for Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```bash
hub init
hub agent register codex --profile codex
hub agent register claude-code --profile claude-code
hub agent heartbeat codex --status active
hub brief --agent codex
hub task create --title "Wire CLI" --intent "Build the first CLI path" --priority normal
hub task claim T000001 --agent codex
hub event push --task T000001 --agent codex --type status --body "started"
hub inbox pull --agent claude-code --format jsonl
hub ui
```

Open the monitor at `http://127.0.0.1:8765`.

## Low-Token Rules

- Keep event bodies short.
- Put large content in `--ref` paths instead of message bodies.
- Use `hub task show T000001 --brief` when an agent only needs current state.
- Use `hub inbox pull --agent <id> --limit 10 --format jsonl` for routine coordination.

## First-Class Profiles

- `codex`
- `claude-code`
- `openclaw`
- `hermes`
