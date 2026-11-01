"""Read-only Dashboard Memory MCP server, using newline-delimited JSON-RPC."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import sys

# -I deliberately excludes cwd. Import only siblings of this resolved script.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

VERSIONS = ("2025-11-25", "2025-06-18", "2024-11-05")


def schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {},
            "required": list(required), "additionalProperties": False}


STRING = {"type": "string", "minLength": 1}
TOOLS = [
    {"name": "memory_ask", "description": "Arbeits-Memory lokal durchsuchen: BM25 oder explizite überfällige Aufgaben. Auswahl, keine Vollständigkeit; Quellen und reife je Treffer. Live nutzt nur GET-Daten, da der Fragen-Endpunkt schreibt.",
     "inputSchema": schema({"question": {**STRING, "maxLength": 8000,
                                           "description": "Suchfrage; überfällig bezieht sich auf explizite Fristen vor heute (Europe/Berlin)."}}, ("question",))},
    {"name": "tasks_list", "description": "Aufgaben aus dem gebundenen Datenstand mit Quellen und reife filtern. Filter werden gemeinsam angewandt; unbekannte Fristen erfüllen keinen Datumsfilter.",
     "inputSchema": schema({
         "status": {**STRING, "enum": ["open", "waiting", "done", "cancelled", "dismissed"]},
         "owner": {**STRING, "description": "Teilstring, ohne Groß-/Kleinschreibung."},
         "matter": {**STRING, "description": "Exakte Themen-ID oder Teilstring im Thementitel."},
         "due_before": {**STRING, "format": "date", "description": "ISO YYYY-MM-DD, exklusiv."},
         "updated_since": {**STRING, "format": "date", "description": "ISO YYYY-MM-DD, inklusiv."},
         "text": {**STRING, "description": "Alle Suchwörter müssen im Aufgabentext vorkommen."}})},
    {"name": "task_get", "description": "Aufgabe über ihre ID lesen, einschließlich Historie, Meetingquellen, Datum und reife. Unbekannte ID ergibt Werkzeugfehler.",
     "inputSchema": schema({"id": STRING}, ("id",))},
    {"name": "matters_list", "description": "Themen der indexierten Aufgaben mit Aufgabenanzahl, Quellen und reife lesen.", "inputSchema": schema()},
    {"name": "meetings_recent", "description": "Neueste Meetings mit Titel, Datum, Zusammenfassung, Quellen und reife lesen; Standard 10, maximal 100.",
     "inputSchema": schema({"n": {"type": "integer", "minimum": 1,
                                  "maximum": 100, "default": 10}})},
]
for tool in TOOLS:
    tool["annotations"] = {"readOnlyHint": True, "destructiveHint": False,
                           "idempotentHint": True, "openWorldHint": False}
TOOL_MAP = {tool["name"]: tool for tool in TOOLS}


def make_backend(mode="snapshot", archive=None):
    if mode == "snapshot":
        from snapshot import SnapshotBackend
        return SnapshotBackend(archive=archive)
    if mode == "live" and archive is None:
        from live import LiveBackend
        return LiveBackend()
    raise ValueError("Invalid configuration")


def valid_arguments(arguments, input_schema):
    if not isinstance(arguments, dict):
        return False
    properties = input_schema["properties"]
    if set(arguments) - set(properties) or any(key not in arguments for key in input_schema["required"]):
        return False
    for key, value in arguments.items():
        rule = properties[key]
        if rule["type"] == "string":
            if not isinstance(value, str) or not value.strip():
                return False
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                return False
            if "enum" in rule and value not in rule["enum"]:
                return False
            if rule.get("format") == "date":
                from datetime import date
                try:
                    if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
                        return False
                except ValueError:
                    return False
        elif type(value) is not int or not rule["minimum"] <= value <= rule["maximum"]:
            return False
    return True


def tool_result(payload, is_error=False):
    # Validate serialization before emitting anything; NaN is not JSON.
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return {"content": [{"type": "text", "text": serialized}],
            "structuredContent": payload, "isError": is_error}


def tool_error(message):
    return tool_result({"source": "unknown", "reife": "unbekannt", "results": [],
                        "error": message}, True)


def rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


class MCPServer:
    def __init__(self, backend_factory=None):
        self.backend_factory = backend_factory or make_backend
        self.backend = None
        self.initialized = False
        self.ready = False

    def handle(self, request):
        request_id = request.get("id") if isinstance(request, dict) else None
        valid_id = type(request_id) is int or isinstance(request_id, str)
        if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
                or not isinstance(request.get("method"), str)
                or ("id" in request and not valid_id)
                or ("params" in request and not isinstance(request["params"], dict))):
            return rpc_error(request_id if valid_id else None, -32600, "Invalid request")
        method = request["method"]
        params = request.get("params", {})
        if "id" not in request:
            if method == "notifications/initialized" and self.initialized and not params:
                self.ready = True
            return None
        if method == "initialize":
            if (self.initialized or not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(params.get("clientInfo"), dict)
                    or any(not isinstance(params["clientInfo"].get(k), str)
                           for k in ("name", "version"))):
                return rpc_error(request_id, -32602, "Invalid initialize parameters")
            self.initialized = True
            requested = params["protocolVersion"]
            result = {"protocolVersion": requested if requested in VERSIONS else VERSIONS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "dashboard-memory", "version": "1.0.0"}}
        elif method == "ping":
            if params:
                return rpc_error(request_id, -32602, "Invalid ping parameters")
            result = {}
        elif not self.ready:
            return rpc_error(request_id, -32000, "Server not initialized")
        elif method == "tools/list":
            if params:
                return rpc_error(request_id, -32602, "Invalid tools/list parameters")
            result = {"tools": TOOLS}
        elif method == "tools/call":
            if (set(params) - {"name", "arguments", "_meta"}
                    or not isinstance(params.get("name"), str)
                    or ("_meta" in params and not isinstance(params["_meta"], dict))):
                return rpc_error(request_id, -32602, "Invalid tools/call parameters")
            name = params["name"]
            if name not in TOOL_MAP:
                return rpc_error(request_id, -32602, "Unknown tool")
            arguments = params.get("arguments", {})
            if not valid_arguments(arguments, TOOL_MAP[name]["inputSchema"]):
                result = tool_error("Invalid tool arguments")
            else:
                if name == "meetings_recent":
                    arguments = {"n": 10, **arguments}
                try:
                    # A backend print must never corrupt the protocol or reveal data.
                    with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
                        if self.backend is None:
                            self.backend = self.backend_factory()
                        payload = getattr(self.backend, name)(**arguments)
                        if not isinstance(payload, dict):
                            raise ValueError("Invalid backend result")
                        result = tool_result(payload)
                except Exception:
                    result = tool_error("Memory source unavailable or request failed")
        else:
            return rpc_error(request_id, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


class _Discard:
    def write(self, value):
        return len(value)

    def flush(self):
        pass


def _reject_constant(value):
    raise ValueError("Invalid JSON constant")


def run_stdio(server, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        try:
            request = json.loads(line, parse_constant=_reject_constant)
        except (ValueError, TypeError, RecursionError):
            response = rpc_error(None, -32700, "Parse error")
        else:
            response = server.handle(request)
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
            output_stream.flush()


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid server configuration\n")


def main(argv=None):
    parser = _ArgumentParser(description="Read-only Dashboard Memory MCP stdio server")
    parser.add_argument("--mode", choices=("snapshot", "live"),
                        default=os.environ.get("DASHBOARD_MEMORY_MODE", "snapshot"))
    parser.add_argument("--archive")
    args = parser.parse_args(argv)
    if args.mode not in ("snapshot", "live") or (args.mode == "live" and args.archive is not None):
        parser.error("Invalid configuration")
    run_stdio(MCPServer(lambda: make_backend(args.mode, args.archive)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
