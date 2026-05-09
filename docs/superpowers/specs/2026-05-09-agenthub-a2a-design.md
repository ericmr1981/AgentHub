# AgentHub A2A Protocol Adoption

Date: 2026-05-09
Status: Design draft
Goal: Add A2A protocol support to AgentHub for cross-platform agent collaboration with zero human intervention.

## Philosophy

AgentHub is a **minimum-viable message router** for multi-agent collaboration:

- It routes messages between agents via A2A protocol
- It broadcasts task events so agents discover work themselves
- It relays handoffs between agents
- It maintains an agent registry
- It does NOT make decisions for agents, match skills, or route intelligently

## Architecture

```
                     A2A JSON-RPC over HTTP
                          POST /a2a
                          
   Agent A ──┐              ┌── A2A Endpoint (a2a.py)
   (Codex)   │              │
   Agent B ──┼── tasks/send─┤── SQLite (events registry)
   (Claude)  │   tasks/list │      │
   Agent C ──┘   tasks/     │      ├── SSE stream → all agents
             subscribe      │      │
                            │      └── UI Monitor
                 ┌──────────┘
                 │
     /.well-known/agent-card (Hub Card)
     GET /api/events/stream (SSE for all agents)
     POST /a2a (JSON-RPC tasks/* methods)
```

## What stays from current AgentHub

- SQLite as source of truth (agents, tasks, events, handoffs tables)
- Core service methods: create_task, claim_task, close_task, block_task, handoff_create, handoff_accept
- Dashboard UI (monitor)
- Testing infrastructure (pytest, TestClient)

## What changes

### NEW: `src/agenthub/a2a.py` — A2A Protocol Endpoint

JSON-RPC 2.0 endpoint at `POST /a2a`. Supports these methods:

| Method | Maps to AgentHub |
|--------|-----------------|
| `tasks/send` | create_task OR event_push via message body type |
| `tasks/list` | list_tasks + list_handoffs |
| `tasks/get` | show_task |
| `tasks/subscribe` | SSE stream for task events |

Message format for `tasks/send`:

```json
{
  "method": "tasks/send",
  "params": {
    "message": {
      "role": "agent",
      "parts": [
        {"text": "Review my PR", "type": "intent"},
        {"data": {"tags": ["code-review", "python"]}, "type": "meta"}
      ]
    }
  }
}
```

The hub interprets the message:
- If part.type == "intent" → creates a new task
- If part.type == "claim" → claims the referenced task
- If part.type == "handoff" → creates a handoff to target agent
- If part.type == "status" → pushes a status event

### NEW: `/.well-known/agent-card` — Hub Card

Returns the hub's own Agent Card:

```json
{
  "name": "AgentHub",
  "description": "Multi-agent coordination hub",
  "version": "1.0",
  "capabilities": {"streaming": true},
  "interfaces": [{"type": "a2a", "url": "http://localhost:8765/a2a"}],
  "skills": [
    {"id": "task-routing", "tags": ["task", "coordination"]},
    {"id": "handoff", "tags": ["handoff", "transfer"]}
  ]
}
```

### NEW: `src/agenthub/registry.py` — Agent Registry

Each agent registers with an Agent Card:

```python
# Agent sends:
POST /a2a
{
  "method": "registry/register",
  "params": {
    "agentCard": {
      "name": "code-reviewer",
      "skills": [
        {"id": "review", "tags": ["python", "code-review"]}
      ]
    }
  }
}
```

Agent Cards stored in SQLite `agents.metadata_json`. Hub maintains heartbeat tracking.

### NEW: SSE Event Stream — replaces `hub watch` polling

```python
@app.get("/api/events/stream")
async def event_stream():
    """SSE endpoint — all agents subscribe here."""
    # Polls events table every 1s
    # Pushes new events as SSE data lines
    # Fields: {type: "task_created"|"task_claimed"|"handoff"|"status", data: {...}}
```

### NEW: `scripts/agent_worker.py` — Agent Brain

Minimal agent daemon. Each agent runs:

```python
# 1. Register with hub via Agent Card
# 2. Subscribe to SSE event stream
# 3. On event: decide whether to act (based on own skills)
# 4. If claim: POST tasks/send with "claim" type
# 5. Do work, POST tasks/send with "status" type
# 6. When done: POST tasks/send with "close" type
# 7. If stuck: POST tasks/send with "handoff" type → target another agent
```

### REMOVED/DEPRECATED

- `hub watch` CLI — replaced by SSE stream
- `hub inbox pull` CLI — replaced by `tasks/list` A2A method
- CLI-based handoff discovery — replaced by SSE push

### KEPT (for human use and testing)

- `hub init`, `hub agent register/heartbeat`
- `hub task create/list/show/claim/block/close`
- `hub handoff create/accept`
- `hub ui`

## Data Flow: End-to-End Example

```
1. Agent A registers:
   POST /a2a {"method": "registry/register", "params": {"agentCard": {...}}}

2. Agent A creates task:
   POST /a2a {"method": "tasks/send", "params": {"message": {"parts": [{"text": "Review my PR", "type": "intent", "data": {"tags": ["code-review"]}}]}}}

3. Hub creates task T000001, pushes SSE event:
   data: {"type": "task_created", "task_id": "T000001", "intent": "Review my PR", "tags": ["code-review"]}

4. Agent B (code-reviewer) sees event, decides to claim:
   POST /a2a {"method": "tasks/send", "params": {"message": {"parts": [{"text": "I'll review", "type": "claim"}], "referenceTaskIds": ["T000001"]}}}

5. Hub updates task owner to B, pushes SSE:
   data: {"type": "task_claimed", "task_id": "T000001", "owner": "code-reviewer"}

6. Agent B works, posts status:
   POST /a2a {"method": "tasks/send", "params": {"message": {"parts": [{"text": "Found 3 issues", "type": "status"}], "referenceTaskIds": ["T000001"]}}}

7. Agent B completes:
   POST /a2a {"method": "tasks/send", "params": {"message": {"parts": [{"text": "All fixed", "type": "close"}], "referenceTaskIds": ["T000001"]}}}

8. Hub marks task done, pushes SSE:
   data: {"type": "task_completed", "task_id": "T000001"}
```

## Testing Strategy

1. **Unit tests**: A2A message parsing, Agent Card validation
2. **Integration tests**: A2A endpoint → service layer → SSE stream
3. **E2E test**: 2 agents via agent_worker.py complete a full claim-work-close cycle without human input
4. **E2E test**: 3 agents via agent_worker.py complete a handoff chain (A creates → B claims → B hands off to C → C closes)
5. **Stress test**: 10 tasks auto-claimed and completed by 3 agents

## Implementation Order

1. `a2a.py` — A2A JSON-RPC endpoint
2. `registry.py` — Agent Card registration and heartbeat
3. SSE event stream — replace polling
4. `scripts/agent_worker.py` — agent daemon
5. E2E tests — prove no-human-intervention flow
6. Cleanup — deprecate polling commands, update docs
