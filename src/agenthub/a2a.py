from __future__ import annotations

from agenthub.errors import HubError
from agenthub.service import HubService
from agenthub.registry import AgentRegistry


class A2AHandler:
    def __init__(self, service: HubService):
        self._svc = service

    def dispatch(self, request_body: dict) -> dict:
        method = request_body.get("method", "")
        req_id = request_body.get("id", "")
        params = request_body.get("params", {})

        try:
            if method == "tasks/send":
                return self._handle_send(req_id, params)
            elif method == "tasks/list":
                return self._handle_list(req_id, params)
            elif method == "tasks/get":
                return self._handle_get(req_id, params)
            elif method == "tasks/subscribe":
                return self._handle_subscribe(req_id, params)
            elif method == "registry/register":
                return self._handle_register(req_id, params)
            elif method == "registry/list":
                return self._handle_registry_list(req_id, params)
            elif method == "registry/get":
                return self._handle_registry_get(req_id, params)
            else:
                return self._error(req_id, -32601, f"Method not found: {method}")
        except HubError as exc:
            return self._error(req_id, -32000, exc.message, exc.code)

    def _handle_send(self, req_id: str, params: dict) -> dict:
        message = params.get("message", {})
        parts = message.get("parts", [])
        refs = message.get("referenceTaskIds", [])
        sender = message.get("messageId", "").split("-")[0]

        for part in parts:
            ptype = part.get("type", "intent")

            if ptype == "intent":
                text = part.get("text", "New task")
                task = self._svc.create_task(text, text, "normal", [])
                return self._ok(req_id, {"task": {"id": task["id"], "status": task["status"]}})

            elif ptype == "claim" and refs:
                result = self._svc.claim_task(refs[0], sender)
                return self._ok(req_id, {"task": {"id": result["id"], "status": result["status"]}})

            elif ptype == "close" and refs:
                text = part.get("text", "completed")
                result = self._svc.close_task(refs[0], sender, text)
                return self._ok(req_id, {"task": {"id": result["id"], "status": result["status"]}})

            elif ptype == "handoff" and refs:
                text = part.get("text", "handing off")
                data = part.get("data", {})
                to_agent = data.get("to_agent", "")
                if to_agent:
                    handoff = self._svc.create_handoff(refs[0], sender, to_agent, text)
                    return self._ok(req_id, {"handoff": {"id": handoff["id"], "status": handoff["status"]}})

            elif ptype == "status" and refs:
                text = part.get("text", "")
                event = self._svc.push_event(refs[0], sender, "status", text, [])
                return self._ok(req_id, {"event": {"id": event["id"], "body": event["body"]}})

        return self._error(req_id, -32602, "No handler matched the message parts")

    def _handle_list(self, req_id: str, params: dict) -> dict:
        tasks = self._svc.list_tasks()
        return self._ok(req_id, {"tasks": tasks})

    def _handle_get(self, req_id: str, params: dict) -> dict:
        task_id = params.get("id", "")
        task = self._svc.show_task(task_id, brief=True)
        return self._ok(req_id, {"task": task})

    def _handle_subscribe(self, req_id: str, params: dict) -> dict:
        return self._ok(req_id, {"stream_url": "/api/events/stream"})

    def _handle_register(self, req_id: str, params: dict) -> dict:
        card = params.get("agentCard", {})
        agent_id = card.get("name", "")
        if not agent_id:
            return self._error(req_id, -32602, "agentCard.name is required")
        registry = AgentRegistry(self._svc)
        registry.register(agent_id, card)
        return self._ok(req_id, {"registered": agent_id})

    def _handle_registry_list(self, req_id: str, params: dict) -> dict:
        registry = AgentRegistry(self._svc)
        return self._ok(req_id, {"agents": registry.list_all()})

    def _handle_registry_get(self, req_id: str, params: dict) -> dict:
        agent_id = params.get("agentId", "")
        if not agent_id:
            return self._error(req_id, -32602, "agentId is required")
        registry = AgentRegistry(self._svc)
        try:
            return self._ok(req_id, {"agent": registry.lookup(agent_id)})
        except HubError as exc:
            return self._error(req_id, -32000, exc.message, exc.code)

    def _ok(self, req_id: str, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id: str, code: int, message: str, data: str | None = None) -> dict:
        err = {"code": code, "message": message}
        if data:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": err}
