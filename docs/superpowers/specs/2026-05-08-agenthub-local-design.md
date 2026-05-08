# AgentHub Local Design

Date: 2026-05-08
Status: Approved draft
Scope: Local-first AgentHub for high-frequency, low-token coordination among Codex, Claude Code, OpenClaw, Hermes Agent, and compatible custom agents.

## Purpose

AgentHub is a local collaboration backplane for multiple agents. It gives agents a shared, low-token way to coordinate work without long chat transcripts or heavyweight orchestration.

The first version focuses on local execution, frequent short updates, reliable handoffs, and a monitor UI for human oversight.

## Goals

- Support high-frequency local coordination between agents.
- Minimize token usage by exchanging short structured events and artifact references.
- Keep the architecture simple, inspectable, and elegant.
- Support Codex, Claude Code, OpenClaw, and Hermes Agent as first-class targets.
- Provide a local monitoring UI for observing agents, tasks, events, handoffs, and health.
- Preserve full history by default while allowing later compaction and archival.

## Non-Goals

- No cloud sync in the first version.
- No public network exposure by default.
- No multi-user permission system in the first version.
- No long conversational memory inside Hub events.
- No requirement that agents use a language-specific SDK.
- No complex workflow orchestration engine in the first version.

## Architecture

AgentHub is a local-first system with SQLite as the source of truth, a Python CLI as the primary agent interface, adapter profiles for supported runtimes, and an optional local monitor UI.

```text
Codex / Claude Code / OpenClaw / Hermes Agent / custom agents
            |
            | hub CLI / adapter profile
            v
      Python Hub Core
            |
            v
   SQLite: .agenthub/hub.db
            ^
            |
      hub ui: local monitor
```

### Core Principles

- SQLite is the only durable fact source.
- The CLI is the stable, low-token interface for agents.
- JSONL is the default machine-readable stream format.
- `pull` is the base inbox protocol.
- `watch` is a convenience layer built on cursor polling.
- Large content stays outside event bodies and is linked through artifact references.
- The UI observes and manages Hub state, but agent coordination does not depend on the UI server.

## Core Concepts

### Agent

An agent is an actor that can create, claim, update, hand off, or complete tasks.

Fields:

- `id`: stable identifier such as `codex`, `claude-code`, `openclaw`, `hermes`, or custom IDs.
- `display_name`: human-readable name.
- `profile_name`: runtime behavior profile.
- `status`: `active`, `idle`, `paused`, or `stale`.
- `last_seen_at`: heartbeat timestamp.
- `metadata_json`: optional runtime metadata.

### Task

A task is the stable unit of work and context.

Fields:

- `id`
- `title`
- `intent`
- `status`: `open`, `claimed`, `blocked`, `done`, or `archived`.
- `owner_agent_id`
- `priority`
- `created_at`
- `updated_at`
- `closed_at`
- `refs_json`
- `summary`

### Event

An event is a short, structured coordination signal.

Fields:

- `id`
- `task_id`
- `type`: `status`, `claim`, `handoff`, `blocked`, `note`, `artifact`, or `heartbeat`.
- `by_agent_id`
- `body`: short text, normally under the configured body budget.
- `refs_json`: optional artifact references.
- `cursor`: monotonically increasing cursor for inbox reads.
- `created_at`

### Handoff

A handoff is an explicit transfer request between agents.

Fields:

- `id`
- `task_id`
- `from_agent_id`
- `to_agent_id`
- `reason`
- `status`: `pending`, `accepted`, or `stale`.
- `created_at`
- `accepted_at`

### ArtifactRef

Artifact references keep large content out of messages.

Fields:

- `kind`: `file`, `url`, `commit`, `log`, or `note`.
- `uri`
- `summary`

## CLI Design

The CLI should be short, scriptable, and safe for agents to call frequently.

### Initialization

```bash
hub init
```

Creates `.agenthub/hub.db`, default profiles, and any required local directories.

### Agents

```bash
hub agent register codex --profile codex
hub agent heartbeat codex --status active
hub agent pause codex
hub agent resume codex
```

### Tasks

```bash
hub task create --title "..." --intent "..." --priority normal --ref ./spec.md
hub task list --status open --format jsonl
hub task show T000123 --brief
hub task claim T000123 --agent codex
hub task block T000123 --agent codex --reason "needs schema"
hub task close T000123 --agent codex --summary "implemented CLI skeleton"
```

### Events and Inbox

```bash
hub event push --task T000123 --agent codex --type status --body "schema done" --ref ./schema.sql
hub inbox pull --agent codex --limit 10 --since cursor123 --format jsonl
hub watch --agent codex --interval 1s --format jsonl
```

`pull` returns unread or cursor-filtered events. `watch` repeatedly queries events and emits one JSON object per line.

### Handoffs

```bash
hub handoff T000123 --from codex --to claude-code --reason "please review edge cases"
hub handoff accept H000456 --agent claude-code
```

### Compaction

```bash
hub compact --older-than 14d --mode summarize
```

Compaction creates summaries and archival records. It does not delete original history by default.

### UI

```bash
hub ui --host 127.0.0.1 --port 8765
```

Starts the local monitor UI. The default bind address must be loopback-only.

## Event Format

Default JSON event shape:

```json
{
  "id": "E000042",
  "type": "status",
  "task_id": "T000007",
  "by_agent": "codex",
  "body": "schema done; refs include migration",
  "refs": [
    {
      "kind": "file",
      "uri": "./schema.sql",
      "summary": "SQLite schema"
    }
  ],
  "created_at": "2026-05-08T19:40:00+08:00"
}
```

## Low-Token Rules

- Event bodies should normally stay under `280` characters.
- `pull` defaults to unread events rather than full task history.
- `--brief` returns current task state and a small recent-event window.
- Large content is represented through `refs`, not copied into event bodies.
- `watch` emits JSONL so agents can consume events incrementally.
- Compaction produces summaries for old activity while keeping original records unless explicitly archived later.

## Adapter Profiles

Profiles describe runtime behavior without forcing each agent to use an SDK.

Example:

```yaml
id: codex
display_name: Codex
inbox_limit: 10
watch_interval_ms: 1000
event_body_budget_chars: 280
preferred_format: jsonl
supports_shell: true
supports_plugin: false
```

### First-Class Runtime Targets

- Codex: direct shell access to the `hub` CLI.
- Claude Code: Bash/tool access to the `hub` CLI.
- OpenClaw: exec tool or gateway bridge access to `hub`; later native plugin support is possible.
- Hermes Agent: persistent shell or plugin access to `hub`; later native plugin support is possible.

The generic compatibility rule is: if an agent can execute a local command or load a thin plugin, it can participate in AgentHub.

## Monitor UI

The monitor UI is a local control tower for observation-first management.

### UI Boundary

- Runs locally through `hub ui`.
- Binds to `127.0.0.1` by default.
- Reads and manages SQLite state through a lightweight local API.
- Does not replace the CLI for agent coordination.
- Does not automatically load large artifact contents.

### Pages

#### Radar

- Active agent count.
- Stale and paused agents.
- Event throughput over 1, 5, and 15 minutes.
- Current blocked task count.
- Recent handoff queue.

#### Tasks

- Task list grouped by `open`, `claimed`, `blocked`, and `done`.
- Owner, priority, age, and artifact reference count.
- Filtering by agent, status, and priority.
- Task detail with brief timeline.

#### Timeline

- Global event stream.
- Filters for agent, task, and event type.
- JSONL source view for copying into agent prompts or debugging logs.

#### Handoffs

- Pending, accepted, and stale handoffs.
- Source and target agents.
- Task, reason, and age.

#### Artifacts

- Artifact reference list.
- Kind, URI, summary, and linked task.
- No automatic large-file ingestion.

#### Health

- SQLite path.
- Database size.
- Event count.
- Compaction candidates.
- Profile status.

### Safe Management Actions

Agent actions:

- Pause agent.
- Resume agent.

Task actions:

- Reassign owner.
- Mark blocked.
- Close with summary.

Handoff actions:

- Mark accepted.
- Mark stale.

History actions:

- Run compact preview.

### Visual Direction

The UI should feel like a local industrial control tower: dense, calm, and scannable.

- Tone: local control tower / industrial observability.
- Color: graphite, fog white, amber warnings, cyan-green active signals.
- Layout: dense dashboard with strong hierarchy and quick scanning.
- Motion: subtle event flashes, short state-change highlights, staggered page loading.
- Typography: engineering-oriented and distinctive, avoiding generic default stacks where feasible.

## Data Model

Initial tables:

```text
agents
- id
- display_name
- profile_name
- status
- last_seen_at
- metadata_json

tasks
- id
- title
- intent
- status
- owner_agent_id
- priority
- created_at
- updated_at
- closed_at
- refs_json
- summary

events
- id
- task_id
- type
- by_agent_id
- body
- refs_json
- cursor
- created_at

inbox_offsets
- agent_id
- last_cursor

handoffs
- id
- task_id
- from_agent_id
- to_agent_id
- reason
- status
- created_at
- accepted_at

compactions
- id
- scope
- summary
- source_event_start
- source_event_end
- created_at
```

## Concurrency and Consistency

- SQLite should use WAL mode.
- Mutating operations such as `claim` and `handoff accept` must run in transactions.
- Task claim must be atomic: if two agents claim the same open task, only one succeeds.
- Inbox reads use cursors so each agent can consume events without relying on large history scans.
- `watch` should not create a second protocol; it should repeatedly query from the cursor and emit JSONL.
- UI management actions must use the same core service layer as the CLI.

## Error Handling

Errors should be structured and concise.

Example:

```json
{
  "ok": false,
  "error": {
    "code": "TASK_ALREADY_CLAIMED",
    "message": "Task T000007 is already claimed by claude-code",
    "hint": "Use hub handoff or task reassign if ownership should change."
  }
}
```

Expected error classes:

- `TASK_NOT_FOUND`
- `TASK_ALREADY_CLAIMED`
- `AGENT_NOT_FOUND`
- `INVALID_EVENT_TYPE`
- `BODY_TOO_LARGE`
- `HANDOFF_NOT_FOUND`
- `DB_LOCK_TIMEOUT`
- `PROFILE_NOT_FOUND`

## Testing Strategy

### Unit Tests

- ID generation.
- JSON and JSONL output formatting.
- Profile loading and defaults.
- Event body budget validation.
- Artifact reference parsing.

### Database Tests

- Schema creation and migration.
- WAL mode configuration.
- Atomic task claim.
- Cursor-based inbox pull.
- Handoff status transitions.

### CLI Tests

- Core commands verify stdout, stderr, exit code, and database side effects.
- JSONL output is valid line by line.
- Structured errors are emitted consistently.

### Integration Tests

- Simulate Codex, Claude Code, OpenClaw, and Hermes Agent profiles.
- Verify task creation, claim, status event, handoff, acceptance, and close flows.
- Verify `pull` and `watch` behavior over short event bursts.

### UI Tests

- Local API endpoints return expected dashboard state.
- Task filters work by status, agent, and priority.
- Timeline renders recent events.
- Safe management actions call the same core mutations as CLI commands.

### Load Smoke Test

- Write many short local events quickly.
- Confirm event insertion, timeline query, and watch polling remain responsive enough for local use.

## Open Questions for Implementation Planning

- Which Python CLI framework should be used: `argparse`, `click`, or `typer`?
- Which local UI stack should be used: server-rendered HTML, FastAPI plus vanilla JS, or FastAPI plus a bundled frontend?
- Should default profiles live as YAML files on disk, in SQLite, or both?
- What should the initial event throughput target be for the smoke test?
- Should `watch` commit inbox offsets automatically or default to peek mode until an agent acknowledges events?

## Recommended First Implementation Slice

Build the smallest complete vertical path:

1. `hub init` creates SQLite schema and default profiles.
2. `hub agent register` and `hub agent heartbeat` work.
3. `hub task create`, `hub task claim`, and `hub event push` work.
4. `hub inbox pull` emits JSONL with cursors.
5. `hub ui` shows Radar, Tasks, and Timeline in read-only mode.

This proves the core coordination loop before adding compaction, richer management actions, or native bridges.
