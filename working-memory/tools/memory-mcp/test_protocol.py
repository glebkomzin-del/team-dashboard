"""Synthetic protocol checks: no archive, network or production access."""

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import server


def request(method, params=None, request_id=1):
    result = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        result["params"] = params
    return result


def initialize(version="2025-11-25"):
    return request("initialize", {"protocolVersion": version, "capabilities": {},
                                  "clientInfo": {"name": "synthetic", "version": "1"}})


class FakeBackend:
    def __init__(self):
        self.calls = []

    def invoke(self, name, **arguments):
        self.calls.append((name, arguments))
        return {"source": "synthetic", "reife": "unbekannt", "results": []}

    def memory_ask(self, **arguments):
        return self.invoke("memory_ask", **arguments)

    def tasks_list(self, **arguments):
        return self.invoke("tasks_list", **arguments)

    def task_get(self, **arguments):
        return self.invoke("task_get", **arguments)

    def matters_list(self, **arguments):
        return self.invoke("matters_list", **arguments)

    def meetings_recent(self, **arguments):
        return self.invoke("meetings_recent", **arguments)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.loads = 0

        def factory():
            self.loads += 1
            return self.backend

        self.server = server.MCPServer(factory)

    def ready(self):
        self.server.handle(initialize())
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def call(self, name, arguments=None, request_id=2):
        params = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        return self.server.handle(request("tools/call", params, request_id))

    def test_versions_capabilities_and_lazy_loading(self):
        for version in (*server.VERSIONS, "2099-01-01"):
            with self.subTest(version=version):
                instance = server.MCPServer(lambda: self.fail("premature source loading"))
                response = instance.handle(initialize(version))["result"]
                self.assertEqual(response["protocolVersion"], version if version in server.VERSIONS else server.VERSIONS[0])
                self.assertEqual(response["capabilities"], {"tools": {"listChanged": False}})
                instance.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
                tools = instance.handle(request("tools/list"))["result"]["tools"]
                self.assertEqual({t["name"] for t in tools}, set(server.TOOL_MAP))
                self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
        self.assertEqual(self.loads, 0)

    def test_lifecycle_ping_notifications_ids(self):
        self.assertEqual(self.server.handle(request("ping", request_id=0))["id"], 0)
        self.assertEqual(self.server.handle(request("tools/list"))["error"]["code"], -32000)
        self.server.handle(initialize())
        self.assertEqual(self.server.handle(request("tools/list"))["error"]["code"], -32000)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.server.handle(request("tools/list", request_id="opaque"))["id"], "opaque")
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 9}}))
        self.assertEqual(self.server.handle(initialize())["error"]["code"], -32602)

    def test_all_tools_forward_arguments_and_default(self):
        self.ready()
        inputs = [("memory_ask", {"question": "synthetic query"}),
                  ("tasks_list", {"status": "open", "owner": "alias", "matter": "m1",
                                  "due_before": "2026-10-14", "updated_since": "2026-10-01", "text": "fixture"}),
                  ("task_get", {"id": "t1"}), ("matters_list", {}), ("meetings_recent", {})]
        for index, (name, arguments) in enumerate(inputs):
            response = self.call(name, arguments, index)
            self.assertEqual(response["id"], index)
            result = response["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertEqual(self.loads, 1)
        self.assertEqual(self.backend.calls[-1], ("meetings_recent", {"n": 10}))
        self.call("meetings_recent", {"n": 100})
        self.assertEqual(self.backend.calls[-1][1], {"n": 100})
        self.call("tasks_list")
        self.assertEqual(self.backend.calls[-1], ("tasks_list", {}))

    def test_invalid_arguments_never_load_source(self):
        self.ready()
        cases = [("memory_ask", {}), ("memory_ask", {"question": " "}),
                 ("memory_ask", {"question": 1}), ("task_get", {"id": None}),
                 ("tasks_list", {"owner": None}), ("tasks_list", {"extra": "x"}),
                 ("tasks_list", {"status": "invalid"}),
                 ("tasks_list", {"due_before": "2026-02-30"}),
                 ("tasks_list", {"updated_since": "20261013"}),
                 ("memory_ask", {"question": "x" * 8001}),
                 ("matters_list", {"write": True}), ("meetings_recent", {"n": True}),
                 ("meetings_recent", {"n": 0}), ("meetings_recent", {"n": 101}),
                 ("meetings_recent", {"n": 1.5}), ("tasks_list", []), ("tasks_list", None)]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                params = {"name": name, "arguments": arguments}
                result = self.server.handle(request("tools/call", params))["result"]
                self.assertTrue(result["isError"])
                self.assertEqual(result["structuredContent"]["source"], "unknown")
                self.assertEqual(result["structuredContent"]["reife"], "unbekannt")
        self.assertEqual(self.loads, 0)

    def test_invalid_requests_and_params_are_sanitized(self):
        self.ready()
        cases = [[], None, {}, {"jsonrpc": "1.0", "method": "ping", "id": 2},
                 request("ping", []), request("ping", request_id=True), request("ping", request_id=None),
                 {"jsonrpc": "2.0", "method": 1, "id": "kept"}]
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(self.server.handle(value)["error"]["code"], -32600)
        for method, params in [("ping", {"unexpected": "private"}), ("tools/list", {"cursor": "private"}),
                               ("tools/call", {}), ("tools/call", {"name": "private_unknown"}),
                               ("tools/call", {"name": "matters_list", "extra": "private"})]:
            response = self.server.handle(request(method, params))
            self.assertEqual(response["error"]["code"], -32602)
            self.assertNotIn("private", json.dumps(response))
        self.assertEqual(self.server.handle(request("absent"))["error"]["code"], -32601)

    def test_initialize_required_shapes(self):
        for params in [{}, {"protocolVersion": 1},
                       {"protocolVersion": "2025-11-25", "capabilities": [], "clientInfo": {}},
                       {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "x"}}]:
            self.assertEqual(server.MCPServer().handle(request("initialize", params))["error"]["code"], -32602)

    def test_execution_errors_and_backend_prints_do_not_leak(self):
        sentinel = "PRIVATE_TOKEN /private/synthetic/path content"

        def failing_factory():
            print(sentinel)
            print(sentinel, file=sys.stderr)
            raise RuntimeError(sentinel)

        self.server.backend_factory = failing_factory
        self.ready()
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            response = self.call("matters_list")
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertTrue(response["result"]["isError"])
        self.assertNotIn(sentinel, json.dumps(response))
        self.assertEqual(response["result"]["structuredContent"]["results"], [])

    def test_invalid_backend_payload_is_execution_error(self):
        self.ready()
        for payload in [None, [], {"bad": float("nan")}, {"bad": object()}]:
            with patch.object(self.backend, "matters_list", return_value=payload):
                self.assertTrue(self.call("matters_list")["result"]["isError"])

    def test_stream_parse_error_and_recovery(self):
        self.ready()
        incoming = io.StringIO('{bad}\n' + json.dumps(request("ping", request_id="after"))
                               + '\nNaN\n' + '[' * 2000 + '0' + ']' * 2000 + '\n')
        output = io.StringIO()
        server.run_stdio(self.server, incoming, output)
        rows = [json.loads(row) for row in output.getvalue().splitlines()]
        self.assertEqual(rows[0]["error"]["code"], -32700)
        self.assertEqual(rows[1], {"jsonrpc": "2.0", "id": "after", "result": {}})
        self.assertEqual(rows[2]["error"]["code"], -32700)
        # Parser recursion limits vary across supported Python versions.
        self.assertIn(rows[3]["error"]["code"], (-32700, -32600))

    def test_subprocess_isolated_stdio_transcript(self):
        messages = [initialize("2024-11-05"), {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    request("tools/list", request_id="tools"), request("ping", request_id=0),
                    request("tools/call", {"name": "memory_ask", "arguments": {}})]
        completed = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT_DIR / "server.py"), "--mode", "snapshot"],
                                   input="\n".join(json.dumps(item) for item in messages) + "\n{bad}\n",
                                   text=True, capture_output=True, timeout=10, cwd="/private/tmp")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        rows = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(rows[1]["id"], "tools")
        self.assertEqual(rows[2]["id"], 0)
        self.assertTrue(rows[3]["result"]["isError"])
        self.assertEqual(rows[4]["error"]["code"], -32700)

    def test_cli_invalid_configuration_hides_paths(self):
        for args in [("--mode", "live", "--archive", "/private/SENTINEL"),
                     ("--mode", "SENTINEL"), ("--unexpected-SENTINEL",)]:
            completed = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT_DIR / "server.py"), *args],
                                       input="", text=True, capture_output=True, timeout=10)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "Invalid server configuration\n")

    def test_factory_modes_import_siblings_lazily(self):
        class Module:
            SnapshotBackend = lambda self, archive=None: ("snapshot", archive)
            LiveBackend = lambda self: ("live",)

        with patch.dict(sys.modules, {"snapshot": Module(), "live": Module()}):
            self.assertEqual(server.make_backend("snapshot", "synthetic"), ("snapshot", "synthetic"))
            self.assertEqual(server.make_backend("live"), ("live",))
            with self.assertRaises(ValueError):
                server.make_backend("live", "synthetic")


if __name__ == "__main__":
    unittest.main()
