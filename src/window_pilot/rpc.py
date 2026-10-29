"""Shared MCP dispatcher for calling hosts: direct stdio and administrator executor."""
from __future__ import annotations

import json

from . import __version__
from .service import INSTRUCTIONS, TOOLS

METHODS = {"initialize", "ping", "tools/list", "tools/call"}
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}


def error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class Dispatcher:
    def __init__(self, service, executor=None):
        self.service, self.executor = service, executor
        self.seen = set()

    def handle(self, request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return error(None, -32600, "Invalid request")
        if "id" not in request:
            return None
        request_id = request["id"]
        if type(request_id) not in (int, str):
            return error(None, -32600, "Invalid request ID")
        if request_id in self.seen or len(self.seen) >= 65536:
            return error(request_id, -32600, "Duplicate ID or connection budget; never replay actions")
        self.seen.add(request_id)
        method, params = request.get("method"), request.get("params", {})
        if method not in METHODS:
            return error(request_id, -32601, "Method not found")
        if not isinstance(params, dict):
            return error(request_id, -32602, "Invalid params")
        try:
            if method == "initialize":
                offered = params.get("protocolVersion")
                result = {"protocolVersion": offered if offered in PROTOCOLS else "2025-03-26",
                          "capabilities": {"tools": {}}, "serverInfo": {"name": "window-pilot", "version": __version__},
                          "instructions": INSTRUCTIONS + "\nConnection loss never authorizes retry. Old tokens must not be automatically rebound."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s in TOOLS]}
            else:
                try:
                    value = self.service.call(params["name"], params.get("arguments", {}))
                    if params["name"] == "health" and self.executor:
                        value["executor"] = self.executor
                    content = []
                    if "image" in value:
                        content.append({"type": "image", "mimeType": value.get("image_mime_type", "image/png"), "data": value.pop("image")})
                    content.insert(0, {"type": "text", "text": json.dumps(value, ensure_ascii=False)})
                    result = {"content": content, "isError": False}
                except Exception as exc:
                    result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
                    if hasattr(exc, "recovery_diagnostic"):
                        result["content"].append({"type": "text", "text": json.dumps(
                            {"recovery_diagnostic": exc.recovery_diagnostic}, ensure_ascii=False)})
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return error(request_id, -32602, str(exc))


def stdio_loop(handle):
    import sys
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        line = stdin.readline(1_048_577)
        if not line:
            return
        if len(line) > 1_048_576:
            raise RuntimeError("MCP request too large; connection stopped, no replay")
        try:
            request = json.loads(line)
        except (ValueError, UnicodeError):
            response = error(None, -32700, "Parse error")
        else:
            response = handle(request)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False).encode("utf8") + b"\n")
            stdout.flush()
