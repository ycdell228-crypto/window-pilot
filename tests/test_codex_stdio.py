"""Opt-in desktop evidence uses only this checkout's native fixture, over real stdio."""
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest

PROJECT = Path(__file__).resolve().parents[1]
PREVIEW = PROJECT / "scripts" / "preview-codex.py"


@unittest.skipUnless(sys.platform == "win32", "requires Windows Python")
class CodexStdioTests(unittest.TestCase):
    def preview(self, *args):
        return subprocess.run([sys.executable, "-I", "-S", "-B", str(PREVIEW),
                               "--python", sys.executable, *args], cwd=PROJECT,
                              capture_output=True, timeout=10)

    def test_preview_modes_and_project_isolation(self):
        for mode in ("direct", "bridge"):
            with self.subTest(mode=mode):
                result = self.preview("--mode", mode, *(["--config", "config.example.json"] if mode == "direct" else []))
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                server = tomllib.loads(result.stdout.decode())["mcp_servers"]["window_pilot_next"]
                self.assertFalse(server["enabled"])
                self.assertEqual(Path(server["cwd"]), PROJECT)
                self.assertEqual(server["args"][:2], ["-I", "-S"])
                self.assertEqual(Path(server["args"][2]), PROJECT / "scripts/runtime_entry.py")
                if mode == "bridge":
                    self.assertEqual(server["args"][3:], ["bridge", "--service-file", str(PROJECT / ".local/admin-service/service.json")])
        with tempfile.TemporaryDirectory() as folder:
            outside = Path(folder) / "config.json"
            outside.write_text("{}")
            refused = self.preview("--config", str(outside))
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(refused.stdout, b"")
            self.assertIn(b"inside this project", refused.stderr)

    def test_dsh_protocol_still_negotiates(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2026-07-28", "capabilities": {},
                              "clientInfo": {"name": "dsh-protocol-check", "version": "1"}}}
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text("{}")
            result = subprocess.run([sys.executable, "-I", "-S", str(PROJECT / "scripts/runtime_entry.py"),
                                     "serve", "--config", str(config)], cwd=PROJECT,
                                    input=(json.dumps(request) + "\n").encode(), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(json.loads(result.stdout)["result"]["protocolVersion"], "2026-07-28")

    def test_generated_direct_entry_delivers_real_fixture_text_image_and_effect(self):
        from window_pilot import win32 as w
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires an interactive local desktop")
        generated = self.preview("--config", "config.example.json")
        self.assertEqual(generated.returncode, 0, generated.stderr.decode())
        server = tomllib.loads(generated.stdout.decode())["mcp_servers"]["window_pilot_next"]
        rows = queue.Queue()
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen([server["command"], *server["args"]], cwd=server["cwd"],
                                       env={**os.environ, **server["env"]}, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=errors)
            def read():
                for line in process.stdout:
                    rows.put(line)
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            sequence = 0
            def request(method, params=None, notification=False):
                nonlocal sequence
                sequence += 1
                value = {"jsonrpc": "2.0", "method": method, "params": params or {}}
                if not notification:
                    value["id"] = sequence
                process.stdin.write((json.dumps(value) + "\n").encode())
                process.stdin.flush()
                if notification:
                    return
                reply = json.loads(rows.get(timeout=12))
                self.assertEqual(reply["id"], sequence)
                self.assertNotIn("error", reply)
                return reply["result"]
            def call(name, **arguments):
                result = request("tools/call", {"name": name, "arguments": arguments})
                self.assertFalse(result["isError"], result)
                self.assertEqual(result["content"][0]["type"], "text")
                return json.loads(result["content"][0]["text"]), result["content"]
            def observe(target, label):
                metadata, content = call("observe", target_id=target, capture_backend="printwindow")
                self.assertEqual([part["type"] for part in content], ["text", "image"])
                self.assertEqual(content[1]["mimeType"], "image/png")
                data = base64.b64decode(content[1]["data"], validate=True)
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", data[16:24]), (metadata["width"], metadata["height"]))
                self.assertEqual(hashlib.sha256(data).hexdigest(), metadata["sha256"])
                evidence = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
                if evidence:
                    destination = Path(evidence).resolve()
                    self.assertTrue(destination.is_relative_to(PROJECT / ".local"))
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / f"stdio-{label}.png").write_bytes(data)
                return metadata
            try:
                initialized = request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                     "clientInfo": {"name": "isolated-stdio-check", "version": "1"}})
                self.assertEqual(initialized["protocolVersion"], "2025-06-18")
                request("notifications/initialized", notification=True)
                tools = request("tools/list")["tools"]
                self.assertEqual(len(tools), 13)
                for tool in tools:
                    self.assertEqual(tool["inputSchema"]["type"], "object")
                health, _ = call("health")
                self.assertEqual(health["executor"]["mode"], "direct_stdio")
                self.assertFalse(health["app_launch"]["enabled"])
                fixture, _ = call("launch_test")
                windows, _ = call("list_windows")
                target = next(row for row in windows["windows"] if row["pid"] == fixture["pid"] and row["klass"] == "WindowPilotFixture")
                self.assertEqual(target["title"], "Window Pilot Test | clicks=0")
                bound, _ = call("bind_window", hwnd=target["hwnd"], access="observe_and_click",
                                purpose="isolated project fixture acceptance", capture_backend="printwindow")
                before = observe(bound["target_id"], "before")
                controls, _ = call("observe_controls", target_id=bound["target_id"], frame_id=before["frame_id"])
                self.assertEqual(controls["status"], "ok", controls)
                self.assertIn("UIA sample button", {node["name"] for node in controls["nodes"]})
                self.assertEqual(controls["frame_id"], before["frame_id"])
                clicked, _ = call("click", target_id=bound["target_id"], frame_id=before["frame_id"], x=40, y=40)
                self.assertEqual(clicked["effect"], "unverified")
                after = observe(bound["target_id"], "after")
                self.assertNotEqual(before["sha256"], after["sha256"])
                windows, _ = call("list_windows")
                self.assertEqual(next(row["title"] for row in windows["windows"] if row["hwnd"] == target["hwnd"]),
                                 "Window Pilot Test | clicks=1")
                call("unbind_window", target_id=bound["target_id"])
                call("close_test")
                health, _ = call("health")
                self.assertIsNone(health["fixture_pid"])
                self.assertFalse(health["faulted"])
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()  # only the exact test child; never another service
                    process.wait(timeout=5)
                reader.join(timeout=2)
                process.stdout.close()
            errors.seek(0)
            self.assertEqual(process.returncode, 0, errors.read().decode("utf8", "replace"))
            self.assertTrue(rows.empty(), "stdout must contain only request-correlated MCP responses")
