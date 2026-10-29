"""Native tests only create project-owned windows. Never launch a helper/game."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1":
            raise unittest.SkipTest("Native UI evidence must be collected on an interactive local desktop")
        if not w.U.GetForegroundWindow():
            raise unittest.SkipTest("No interactive foreground desktop")
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / "config.local.json"
        cls.config.write_text('{"window_control":{"capture_backend":"printwindow"}}', encoding="utf8")
        cls.service = Service(cls.config)
        launched = cls.service.call("launch_test", {})
        cls.hwnd = launched["windows"][0]["hwnd"]
        cls.service.call("list_windows", {})
        cls.bound = cls.service.call("bind_window", {"hwnd": cls.hwnd, "access": "observe_and_click", "purpose": "project-owned fixture validation", "capture_backend": "printwindow"})
        cls.target_id = cls.bound["target_id"]

    @classmethod
    def tearDownClass(cls):
        cls.service.dispose()
        cls.temp.cleanup()

    def observe(self):
        return self.service.call("observe", {"target_id": self.target_id})

    def test_01_occluded_capture_is_target_pixels(self):
        import base64
        observation = self.observe()
        data = base64.b64decode(observation["image"])
        compressed, offset = b"", 8
        while offset < len(data):
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            if data[offset + 4:offset + 8] == b"IDAT":
                compressed += data[offset + 8:offset + 8 + size]
            offset += size + 12
        raw = zlib.decompress(compressed)
        stride = observation["width"] * 3 + 1
        self.assertEqual(raw[10 * stride + 1 + 10 * 3:10 * stride + 1 + 10 * 3 + 3], bytes([0xdd, 0x33, 0x22]))
        self.assertIn("before", observation["desktop_observation"])
        self.assertIn("after", observation["desktop_observation"])
        self.assertEqual(observation["capture_method"], "PrintWindow")

    def test_02_background_click_hits_only_test(self):
        observation = self.observe()
        original = w.text(self.hwnd)
        result = self.service.call("click", {"target_id": self.target_id, "frame_id": observation["frame_id"], "x": 40, "y": 40})
        self.assertNotEqual(original, w.text(self.hwnd))
        self.assertIn("clicks=1", w.text(self.hwnd))
        self.assertEqual(result["effect"], "unverified")
        self.assertTrue(result["input_sent"])
        self.assertFalse(self.service.faulted)
        print("ACTUAL_NATIVE_CLICK_DIAGNOSTIC " + json.dumps(result["desktop_observation"]), flush=True)
        with self.assertRaisesRegex(w.PilotError, "STALE_FRAME"):
            self.service.fresh_frame(observation["frame_id"])

    def test_03_bad_window_is_error(self):
        for hwnd in (0, 0xffff, -100):
            with self.assertRaises(w.PilotError):
                w.identity(hwnd)
        with self.assertRaisesRegex(w.PilotError, "TARGET_NOT_ALLOWED"):
            self.service.role(w.identity(w.desktop_state()["foreground"]))

    def test_04_stale_frame_and_bounds_rejected(self):
        frame = self.observe()
        self.service.frames[frame["frame_id"]]["time"] -= 31
        with self.assertRaisesRegex(w.PilotError, "STALE_FRAME"):
            self.service.fresh_frame(frame["frame_id"])
        target = self.service.target(self.target_id)
        for x, y in [(-1, 1), (99999, 0), (True, 0)]:
            with self.assertRaisesRegex(w.PilotError, "INVALID_POINT"):
                w.click(target, w.geometry(self.hwnd), x, y)
        with self.assertRaisesRegex(w.PilotError, "STALE_FRAME"):
            w.click(target, (1, 1), 0, 0)

    def test_05_daily_gate(self):
        with self.assertRaisesRegex(w.PilotError, "DAILY_LOCKED"):
            self.service.daily_gate()

    def test_06_blank_frame_rejected(self):
        w.post(self.hwnd, 0x8001, 1)
        time.sleep(0.1)
        try:
            with self.assertRaisesRegex(w.PilotError, "BLANK_FRAME"):
                self.observe()
        finally:
            w.post(self.hwnd, 0x8001, 0)
            time.sleep(0.1)

    def test_07_capture_worker_timeout_terminates(self):
        w.post(self.hwnd, 0x8002)
        time.sleep(0.1)
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(w.PilotError, "CAPTURE_TIMEOUT"):
                w.capture(self.service.target(self.target_id), timeout=1)
            self.assertLess(time.monotonic() - started, 3)
        finally:
            time.sleep(max(0, 8.2 - (time.monotonic() - started)))
        # The human may use the browser throughout this wait. Capture is HWND-only.

    def test_08_capture_failure_has_no_fallback(self):
        result = subprocess.CompletedProcess([], 1, b"", b"CAPTURE_FAILED")
        with patch("window_pilot.win32.subprocess.run", return_value=result):
            with self.assertRaisesRegex(w.PilotError, "CAPTURE_FAILED"):
                self.observe()

    def test_09_identity_reuse_rejected(self):
        from dataclasses import replace
        target = self.service.target(self.target_id)
        with self.assertRaisesRegex(w.PilotError, "STALE_WINDOW"):
            w.verify(replace(target, created=target.created + 1))

    def test_10_desktop_changes_do_not_block_real_fixture_clicks(self):
        # Only desktop snapshots are controlled. Message dispatch, the target,
        # capture and its click counter are real; this is not a claim of human activity.
        before = {"foreground": 123, "cursor": [0, 0]}
        cases = [
            ({"foreground": 123, "cursor": [100, 200]}, True, False, False),
            ({"foreground": 456, "cursor": [0, 0]}, False, True, False),
            ({"foreground": 456, "cursor": [100, 200]}, True, True, False),
            ({"foreground": self.hwnd, "cursor": [100, 200]}, True, True, True),
        ]
        for after, cursor_changed, foreground_changed, target_became_foreground in cases:
            with self.subTest(after=after):
                frame = self.observe()
                count = int(w.text(self.hwnd).rsplit("=", 1)[1])
                with patch.object(w, "desktop_state", side_effect=[before, after]), patch.object(w, "post", wraps=w.post) as posted:
                    result = self.service.call("click", {"target_id": self.target_id, "frame_id": frame["frame_id"], "x": 40, "y": 40})
                self.assertEqual(posted.call_count, 2)
                self.assertTrue(all(call.args[0] == self.hwnd for call in posted.call_args_list))
                self.assertEqual([call.args[1] for call in posted.call_args_list], [0x0201, 0x0202])
                self.assertEqual(int(w.text(self.hwnd).rsplit("=", 1)[1]), count + 1)
                self.assertFalse(self.service.faulted)
                self.assertEqual(result["effect"], "unverified")
                diagnostic = result["desktop_observation"]
                self.assertTrue(diagnostic["changed"])
                self.assertEqual(diagnostic["cursor_changed"], cursor_changed)
                self.assertEqual(diagnostic["foreground_changed"], foreground_changed)
                self.assertEqual(diagnostic["target_became_foreground"], target_became_foreground)
                self.assertIn("unknown", diagnostic["attribution"])
                with self.assertRaisesRegex(w.PilotError, "STALE_FRAME"):
                    self.service.fresh_frame(frame["frame_id"])

    def test_11_observation_allows_concurrent_human_cursor_use(self):
        before = {"foreground": 123, "cursor": [0, 0]}
        after = {"foreground": 456, "cursor": [1, 2]}
        with patch.object(w, "desktop_state", side_effect=[before, after]):
            result = self.observe()
        self.assertTrue(result["desktop_observation"]["changed"])




@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class ProtocolTests(unittest.TestCase):
    def test_stdio_handshake_tools_and_removed_tools_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.local.json"
            config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start_pair", "arguments": {"pair": "ww"}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "bind_window", "arguments": {"hwnd": 0}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "click", "arguments": {"target_id": "x", "frame_id": "x", "x": True, "y": 1}}},
                {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "arm_task_monitor", "arguments": {"target_id": "x", "task": "DailyTask", "request_id": "locked-test"}}},
            ]
            result = subprocess.run([sys.executable, "-m", "window_pilot", "serve", "--config", str(config)],
                                    input="".join(json.dumps(r) + "\n" for r in requests).encode(), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            rows = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[0]["result"]["protocolVersion"], "2025-03-26")
            self.assertEqual(rows[0]["result"]["serverInfo"]["name"], "window-pilot")
            self.assertNotIn("DSH", rows[0]["result"]["instructions"])
            self.assertEqual({tool["name"] for tool in rows[1]["result"]["tools"]},
                             {"health", "window_control", "list_windows", "bind_window", "unbind_window", "observe", "observe_controls", "control_action",
                              "click", "foreground_action", "launch_app", "launch_test", "close_test"})
            for row in rows[2:]:
                self.assertTrue(row["result"]["isError"])
            self.assertIn("UNKNOWN_TOOL", rows[2]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
