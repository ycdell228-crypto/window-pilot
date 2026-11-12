"""Tool discovery and guide availability; native checks touch only an owned fixture."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from window_pilot import guides

if sys.platform == "win32":
    from window_pilot.service import Service
    from window_pilot.rpc import Dispatcher
    from window_pilot import win32 as w

PROJECT = Path(__file__).resolve().parents[1]
PRODUCTION = {"browser_session", "begin_window_session", "act_and_observe", "end_window_session",
              "input_control", "get_window_state", "health", "window_control", "list_windows",
              "bind_window", "unbind_window", "control_action", "click", "foreground_action", "launch_app"}


class GuideAvailabilityTests(unittest.TestCase):
    def test_current_shipped_guides_are_readable(self):
        self.assertTrue(guides.guides_available())

    def test_each_missing_guide_is_reported_and_restoring_it_recovers(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(guides, "guide_root", return_value=Path(directory)):
            for name in guides.FILES:
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Guide", encoding="utf8")
            self.assertTrue(guides.guides_available())
            for name in guides.FILES:
                path = Path(directory) / name
                path.unlink()
                self.assertFalse(guides.guides_available(), name)
                path.write_text("# Guide", encoding="utf8")
                self.assertTrue(guides.guides_available(), name)

    def test_empty_invalid_utf8_and_directory_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(guides, "guide_root", return_value=Path(directory)):
            for name in guides.FILES:
                path = Path(directory) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Guide", encoding="utf8")
            entry = Path(directory) / "SKILL.md"
            for data in (b" \n\t", b"\xff\xfe"):
                entry.write_bytes(data)
                self.assertFalse(guides.guides_available())
            entry.unlink()
            entry.mkdir()
            self.assertFalse(guides.guides_available())


@unittest.skipUnless(sys.platform == "win32", "requires Windows service")
class ToolSurfaceTests(unittest.TestCase):
    def test_default_service_refuses_both_self_test_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}")
            service = Service(config)
            try:
                for name in ("launch_test", "close_test"):
                    with self.assertRaisesRegex(w.PilotError, "SELF_TEST_TOOLS_DISABLED"):
                        service.call(name, {})
                self.assertIsNone(service.fixture)
            finally:
                service.dispose()

    def test_invalid_policy_fails_before_creating_service_resources(self):
        for policy in (None, [], {"self_test": "true"}, {"self_test": 1}, {"profile": "other"}, {"unknown": True}):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / "config.json"
                config.write_text(json.dumps({"tools": policy}))
                with self.assertRaisesRegex(w.PilotError, "INVALID_TOOL_POLICY"):
                    Service(config)
                self.assertFalse((Path(directory) / ".local").exists())

    def test_real_stdio_profiles_and_unlisted_calls(self):
        for profile in ("compact", "legacy"):
            for self_test in (False, True):
                with self.subTest(profile=profile, self_test=self_test), tempfile.TemporaryDirectory() as directory:
                    config = Path(directory) / "config.json"
                    config.write_text(json.dumps({"tools": {"profile": profile, "self_test": self_test}}))
                    calls = [("tools/list", {})]
                    # Enabled launch_test is exercised only in the opt-in native test below.
                    if not self_test:
                        calls += [("tools/call", {"name": name, "arguments": {}})
                                  for name in ("launch_test", "close_test")]
                    calls += [("tools/call", {"name": name, "arguments": {"target_id": "missing"}})
                              for name in ("observe", "observe_controls")]
                    calls += [("ping", {})]
                    requests = [{"jsonrpc": "2.0", "id": index, "method": method, "params": params}
                                for index, (method, params) in enumerate(calls, 1)]
                    process = subprocess.run([sys.executable, "-I", "-S", str(PROJECT / "scripts/runtime_entry.py"),
                        "serve", "--config", str(config)], cwd=PROJECT,
                        input="".join(json.dumps(row) + "\n" for row in requests),
                        capture_output=True, text=True, encoding="utf8", timeout=15)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    rows = [json.loads(line) for line in process.stdout.splitlines()]
                    self.assertEqual(len(rows), len(requests))
                    expected = PRODUCTION | ({"observe", "observe_controls"} if profile == "legacy" else set())
                    expected |= {"launch_test", "close_test"} if self_test else set()
                    tools = rows[0]["result"]["tools"]
                    self.assertEqual({tool["name"] for tool in tools}, expected)
                    self.assertEqual(len(tools), len(expected))
                    for request, row in zip(requests[1:-1], rows[1:-1]):
                        result = row["result"]
                        self.assertTrue(result["isError"], row)
                        name = request["params"]["name"]
                        error = ("SELF_TEST_TOOLS_DISABLED" if name.endswith("_test") else
                                 "LEGACY_OBSERVER_DISABLED" if profile == "compact" else "UNKNOWN_TARGET")
                        self.assertIn(error, result["content"][0]["text"])
                    self.assertEqual(rows[-1]["result"], {})


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") == "1",
                     "own-fixture desktop acceptance is opt-in")
class ToolSurfaceNativeTests(unittest.TestCase):
    def test_compact_observation_click_recovery_and_health_without_guide_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"tools": {"self_test": True},
                                          "window_control": {"capture_backend": "printwindow"}}))
            service = Service(config)
            dispatch = Dispatcher(service)
            sequence = 0
            def rpc(method, params):
                nonlocal sequence
                sequence += 1
                result = dispatch.handle({"jsonrpc": "2.0", "id": sequence, "method": method, "params": params})
                self.assertNotIn("error", result)
                return result["result"]
            def call(name, **arguments):
                result = rpc("tools/call", {"name": name, "arguments": arguments})
                self.assertFalse(result["isError"], result)
                return json.loads(result["content"][0]["text"]), result["content"]
            try:
                health, _ = call("health")
                self.assertTrue(health["guides_available"])
                with patch.object(guides, "guide_root", return_value=Path(directory) / "absent-guides"):
                    unavailable, _ = call("health")
                    self.assertFalse(unavailable["guides_available"])
                    status, _ = call("input_control", operation="status")
                    self.assertFalse(status["stopped"])
                launched, _ = call("launch_test")
                hwnd = launched["windows"][0]["hwnd"]
                self.assertNotEqual(w.U.GetForegroundWindow(), hwnd)
                call("list_windows")
                bound, _ = call("bind_window", hwnd=hwnd, access="observe_and_click", purpose="owned tool-surface acceptance")
                token = bound["target_id"]
                state, _ = call("get_window_state", target_id=token, include_accessibility=False, include_related_windows=False)
                frame = state["screenshot"]["frame_id"]
                call("click", target_id=token, frame_id=frame, x=40, y=40)
                self.assertIn("clicks=1", w.text(hwnd))
                call("window_control", target_id=token, operation="release")
                prepared, _ = call("window_control", target_id=token, operation="prepare_recovery")
                self.assertEqual(prepared["preparation"], "review_required")
                recovered, _ = call(prepared["next_call_after_review"]["name"], **prepared["next_call_after_review"]["arguments"])
                self.assertEqual(recovered["next_call"]["name"], "get_window_state")
                after, images = call(recovered["next_call"]["name"], **recovered["next_call"]["arguments"])
                self.assertNotEqual(after["screenshot"]["frame_id"], frame)
                self.assertIn("clicks=1", w.text(hwnd))
                controls, _ = call("get_window_state", target_id=token, include_screenshot=False, include_text=False,
                                   include_related_windows=False)
                self.assertIsNone(controls["screenshot"])
                self.assertTrue(controls["accessibility"]["nodes"])
                combined, _ = call("get_window_state", target_id=token, include_related_windows=False)
                self.assertIsNotNone(combined["screenshot"])
                self.assertTrue(combined["accessibility"]["nodes"])
                self.assertNotEqual(w.U.GetForegroundWindow(), hwnd)
                evidence = PROJECT / ".local/tool-surface-native"
                evidence.mkdir(parents=True, exist_ok=True)
                image = next(part for part in images if part["type"] == "image")
                suffix = ".png" if image["mimeType"] == "image/png" else ".jpg"
                (evidence / ("after" + suffix)).write_bytes(base64.b64decode(image["data"]))
                (evidence / "result.json").write_text(json.dumps({"tool_count": len(rpc("tools/list", {})["tools"]),
                    "guides_available": health["guides_available"], "missing_guides_reported": not unavailable["guides_available"],
                    "health_and_status_without_guides": True, "click_count": 1, "recover_replayed_input": False,
                    "recovery_next_tool": recovered["next_call"]["name"], "screenshot_and_controls_modes": True}, indent=2))
                call("close_test")
                self.assertIsNone(service.fixture)
            finally:
                service.dispose()
