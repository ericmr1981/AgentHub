#!/usr/bin/env python3
"""Agent Worker — minimal daemon that auto-participates in AgentHub.

Usage:
    python scripts/agent_worker.py --agent myname --skills python,code-review --hub http://localhost:8765

The worker:
    1. Registers with hub via Agent Card
    2. Subscribes to SSE event stream
    3. On event: tries to claim the referenced task
    4. Simulates work then closes
"""

import argparse
import http.client
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import URLError


def register(hub_url: str, agent_id: str, skills: list[str]):
    card = {
        "name": agent_id,
        "description": f"Agent {agent_id}",
        "skills": [{"id": s.strip(), "tags": [s.strip()]} for s in skills],
        "url": f"{hub_url}/a2a",
    }
    body = json.dumps({
        "jsonrpc": "2.0", "id": "reg-1",
        "method": "registry/register",
        "params": {"agentCard": card},
    }).encode()
    req = urllib.request.Request(f"{hub_url}/a2a", data=body, headers={"Content-Type": "application/json"})
    return _do(req)


def send(hub_url: str, agent_id: str, part_type: str, text: str, refs: list[str] = None, data: dict = None):
    part = {"text": text, "type": part_type}
    if data:
        part["data"] = data
    msg = {
        "messageId": f"{agent_id}-{int(time.time())}",
        "role": "agent",
        "parts": [part],
    }
    if refs:
        msg["referenceTaskIds"] = refs
    body = json.dumps({
        "jsonrpc": "2.0", "id": f"{agent_id}-{int(time.time())}",
        "method": "tasks/send",
        "params": {"message": msg},
    }).encode()
    req = urllib.request.Request(f"{hub_url}/a2a", data=body, headers={"Content-Type": "application/json"})
    return _do(req)


def subscribe(hub_url: str, agent_id: str):
    parts = urllib.parse.urlparse(hub_url)
    host = parts.hostname or "localhost"
    port = parts.port or 80
    path = "/api/events/stream"

    print(f"[{agent_id}] Watching {hub_url}{path} ...", flush=True)

    conn = http.client.HTTPConnection(host, port, timeout=30)
    conn.request("GET", path)
    resp = conn.getresponse()

    if resp.status != 200:
        print(f"  [!] SSE connection failed: {resp.status} {resp.reason}", file=sys.stderr, flush=True)
        return

    try:
        while True:
            line = resp.fp.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith(b"data: "):
                try:
                    event = json.loads(line[6:])
                    _handle_event(hub_url, agent_id, event)
                except json.JSONDecodeError:
                    pass
    finally:
        conn.close()


def _handle_event(hub_url: str, agent_id: str, event: dict):
    task_id = event.get("task_id") or event.get("id", "")
    body = event.get("body", "")
    by = event.get("by_agent_id", "")
    etype = event.get("type", "")

    if by == agent_id or not task_id:
        return

    # Try to claim any task-related event
    print(f"[{agent_id}] Saw event type={etype} from {by}: {body[:60]}", flush=True)
    result = send(hub_url, agent_id, "claim", "I'll take this", refs=[task_id])
    if result and "error" not in result and result.get("result", {}).get("task", {}).get("status") == "claimed":
        print(f"[{agent_id}] Claimed {task_id}", flush=True)
        time.sleep(random.uniform(0.5, 2.0))
        send(hub_url, agent_id, "status", f"Working (by {agent_id})", refs=[task_id])
        time.sleep(random.uniform(0.3, 1.0))
        result = send(hub_url, agent_id, "close", "Done!", refs=[task_id])
        if result and "error" not in result:
            print(f"[{agent_id}] Completed {task_id}", flush=True)


def _do(req):
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except URLError as e:
        print(f"  [!] Error: {e}", file=sys.stderr, flush=True)
        return None


def main():
    parser = argparse.ArgumentParser(description="Agent Worker")
    parser.add_argument("--agent", required=True, help="Agent ID/name")
    parser.add_argument("--skills", default="general", help="Comma-separated skill tags")
    parser.add_argument("--hub", default="http://localhost:8765", help="Hub URL")
    args = parser.parse_args()

    skills_list = [s.strip() for s in args.skills.split(",")]

    result = register(args.hub, args.agent, skills_list)
    if result and "error" not in result:
        print(f"[{args.agent}] Registered with skills: {skills_list}", flush=True)
    else:
        print(f"[{args.agent}] Registration issue: {result}", file=sys.stderr, flush=True)

    try:
        subscribe(args.hub, args.agent)
    except KeyboardInterrupt:
        print(f"\n[{args.agent}] Shutting down.", flush=True)


if __name__ == "__main__":
    main()
