"""Real targeted receiver effects and narrow fault injection; project fixture only."""
import base64
import json
import os
from pathlib import Path
import sys
import struct
import tempfile
import time
import unittest
import zlib
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class MouseNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            raise unittest.SkipTest("requires interactive local desktop")
        cls.evidence = []

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = Path(self.temp.name) / "config.json"
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        self.service = Service(config)
        try:
            fixture = self.service.call("launch_test", {})
            self.hwnd = fixture["windows"][0]["hwnd"]
            self.service.call("list_windows", {})
            self.token = self.service.call("bind_window", {"hwnd": self.hwnd, "access": "observe_and_mouse",
                                                          "purpose": "project-owned mouse acceptance", "capture_backend": "printwindow"})["target_id"]
        except Exception:
            self.service.dispose(); self.temp.cleanup()
            raise

    def tearDown(self):
        self.service.call("close_test", {})
        self.service.dispose()
        self.temp.cleanup()
        destination = self.destination()
        if destination:
            (destination / "mouse-effects.json").write_text(json.dumps(self.evidence, ensure_ascii=False, indent=2), encoding="utf8")

    def destination(self):
        value = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if not value:
            return None
        path = Path(value).resolve()
        self.assertTrue(path.is_relative_to(Path(__file__).resolve().parents[1] / ".local"))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def observe(self, label=None, token=None):
        result = self.service.call("observe", {"target_id": token or self.token})
        if label and self.destination():
            (self.destination() / (label + ".png")).write_bytes(base64.b64decode(result["image"]))
        return result

    def state(self):
        # Receiver-owned fixture counters, not the dispatcher's expected message plan.
        result = []
        for field in range(10):
            value = w.C.c_size_t()
            w.check(w.U.SendMessageTimeoutW(self.hwnd, 0x800a, field, 0, 2, 1000, w.C.byref(value)), "fixture-only state query")
            result.append(w.C.c_ssize_t(value.value).value)
        return dict(zip(("releases", "single_downs", "doubles", "rights", "vertical", "horizontal", "screen_x", "screen_y", "receiver", "context_open"), result))

    def click(self, frame, **parameters):
        return self.service.call("click", {"target_id": self.token, "frame_id": frame["frame_id"], "x": 300, "y": 100, **parameters})

    def viewport_marker(self, frame):
        self.assertEqual(frame["image_mime_type"], "image/png")
        png = base64.b64decode(frame["image"])
        offset, compressed = 8, b""
        while offset < len(png):
            size = struct.unpack(">I", png[offset:offset + 4])[0]
            if png[offset + 4:offset + 8] == b"IDAT":
                compressed += png[offset + 8:offset + 8 + size]
            offset += size + 12
        raw = zlib.decompress(compressed)
        stride = frame["width"] * 3 + 1  # the project's native PNG encoder uses unfiltered RGB rows
        for y in range(60, 190):
            for x in range(260, 480):
                start = y * stride + 1 + x * 3
                if raw[start:start + 3] == b"\xff\x00\xff":
                    return [x, y]
        self.fail("fixture viewport marker missing from actual captured pixels")

    def test_real_right_double_and_both_scroll_directions(self):
        frame = self.observe("00-before")
        plans = [({}, {"releases": 1, "single_downs": 1, "doubles": 0}),
                 ({"action": "right_click"}, {"rights": 1, "context_open": 1}),
                 ({"action": "left_double_click"}, {"releases": 3, "single_downs": 2, "doubles": 1}),
                 ({"action": "scroll", "axis": "vertical", "steps": 2}, {"vertical": 240}),
                 ({"action": "scroll", "axis": "vertical", "steps": -3}, {"vertical": -120}),
                 ({"action": "scroll", "axis": "horizontal", "steps": 1}, {"horizontal": 120}),
                 ({"action": "scroll", "axis": "horizontal", "steps": -2}, {"horizontal": -120})]
        for index, (parameters, expected) in enumerate(plans, 1):
            result = self.click(frame, **parameters)
            self.assertEqual(result["effect"], "unverified")
            updated = self.observe(f"{index:02}-after")
            actual = self.state()
            for key, value in expected.items():
                self.assertEqual(actual[key], value, (parameters, actual))
            receiver = result["click_evidence"]["receiver"]
            self.assertEqual(receiver["klass"], "WindowPilotMouseSurface")
            self.assertEqual(actual["receiver"], receiver["hwnd"])
            self.assertNotEqual(frame["sha256"], updated["sha256"])
            if parameters.get("action") == "scroll":
                point = w.W.POINT(300, 100)
                w.check(w.U.ClientToScreen(self.hwnd, w.C.byref(point)), "independent root-to-screen conversion")
                self.assertEqual((actual["screen_x"], actual["screen_y"]), (point.x, point.y))
                self.assertNotEqual((point.x, point.y), (40, 40))  # receiver client coords must not be used for wheel
                before_marker, after_marker = self.viewport_marker(frame), self.viewport_marker(updated)
                if parameters["axis"] == "vertical":
                    self.assertGreater((after_marker[1] - before_marker[1]) * parameters["steps"], 0)
                else:
                    self.assertLess((after_marker[0] - before_marker[0]) * parameters["steps"], 0)
            else:
                before_marker = after_marker = None
            self.evidence.append({"action": parameters or {"action": "default_left"}, "receiver_state": actual,
                                  "viewport_marker_before": before_marker, "viewport_marker_after": after_marker,
                                  "new_image_confirmed": True, "dispatch_evidence": result["click_evidence"]})
            frame = updated
        self.assertFalse(self.service.faulted)

    def test_partial_double_preserves_three_sent_messages_and_no_replay(self):
        frame = self.observe()
        real_post, calls = w.post, []
        def interrupted(hwnd, message, wp=0, lp=0):
            calls.append(message)
            if len(calls) == 4:
                raise w.PilotError("controlled final release failure")
            return real_post(hwnd, message, wp, lp)
        with patch.object(w, "post", side_effect=interrupted):
            with self.assertRaisesRegex(w.PilotError, "POST_DISPATCH_ERROR: input_sent=true.*up_posted=false") as failed:
                self.click(frame, action="left_double_click")
            evidence = failed.exception.click_evidence
            self.assertEqual([row["state"] for row in evidence["messages"]], ["posted", "posted", "posted", "not_posted"])
            self.assertTrue(self.service.faulted)
            with self.assertRaisesRegex(w.PilotError, "STALE_FRAME|WINDOW_INPUT_FAULTED"):
                self.click(frame, action="left_double_click")
            updated = self.observe("partial-double")
            with self.assertRaisesRegex(w.PilotError, "BINDING_INPUT_FAULTED"):
                self.click(updated, action="left_double_click")
        self.assertEqual(len(calls), 4)
        actual = self.state()
        self.assertEqual((actual["releases"], actual["doubles"]), (1, 1))
        self.evidence.append({"controlled_failure": "double final release", "receiver_state": actual,
                              "dispatch_evidence": evidence, "replay_refused": True})

    def test_wheel_barrier_failure_preserves_actual_input_and_stops(self):
        frame = self.observe()
        with patch.object(w.U, "SendMessageTimeoutW", return_value=0):
            with self.assertRaisesRegex(w.PilotError, "POST_DISPATCH_ERROR: input_sent=true.*message barrier") as failed:
                self.click(frame, action="scroll", steps=1)
        self.observe("wheel-barrier-failure")
        actual = self.state()
        self.assertEqual(actual["vertical"], 120)
        self.assertTrue(self.service.faulted)
        self.assertEqual(failed.exception.click_evidence["messages"][0]["state"], "posted")
        self.evidence.append({"controlled_failure": "wheel barrier", "receiver_state": actual,
                              "dispatch_evidence": failed.exception.click_evidence, "binding_faulted": True})

    def test_double_without_class_support_and_old_left_scope_refuse(self):
        frame = self.observe()
        with self.assertRaisesRegex(w.PilotError, "DOUBLE_CLICK_CLASS_UNSUPPORTED") as failed:
            self.service.call("click", {"target_id": self.token, "frame_id": frame["frame_id"], "x": 300, "y": 205,
                                        "action": "left_double_click"})
        self.assertEqual(failed.exception.click_evidence["messages"], [])
        self.assertEqual(self.state()["releases"], 0)
        self.service.call("list_windows", {})
        old_token = self.service.call("bind_window", {"hwnd": self.hwnd, "access": "observe_and_click", "purpose": "left-only fixture scope"})["target_id"]
        old_frame = self.observe(token=old_token)
        with self.assertRaisesRegex(w.PilotError, "MOUSE_ACTION_ACCESS_REQUIRED"):
            self.service.call("click", {"target_id": old_token, "frame_id": old_frame["frame_id"], "x": 300, "y": 100,
                                        "action": "right_click"})
        self.assertEqual(self.state()["rights"], 0)
        self.evidence.append({"rejected": ["DOUBLE_CLICK_CLASS_UNSUPPORTED", "MOUSE_ACTION_ACCESS_REQUIRED"], "no_input_confirmed": True})

    def test_negative_screen_coordinate_wheel_reaches_exact_child(self):
        w.api(w.U, "SetWindowPos", w.W.BOOL, w.W.HWND, w.W.HWND, w.C.c_int, w.C.c_int, w.C.c_int, w.C.c_int, w.W.UINT)
        w.check(w.U.SetWindowPos(self.hwnd, None, -700, 100, 0, 0, 0x15), "move own fixture without activation")
        frame = self.observe()
        result = self.click(frame, action="scroll", axis="horizontal", steps=-1)
        updated = self.observe("negative-screen-wheel")
        actual = self.state()
        point = w.W.POINT(300, 100)
        w.check(w.U.ClientToScreen(self.hwnd, w.C.byref(point)), "independent negative screen point")
        self.assertLess(point.x, 0)
        self.assertEqual((actual["screen_x"], actual["screen_y"]), (point.x, point.y))
        self.assertEqual(actual["horizontal"], -120)
        self.assertNotEqual(frame["sha256"], updated["sha256"])
        self.evidence.append({"negative_screen_wheel": actual, "new_image_confirmed": True,
                              "dispatch_evidence": result["click_evidence"]})

    def test_expired_double_group_stops_after_first_single_without_fallback(self):
        frame = self.observe()
        real_post = w.post
        def slow_first_release(hwnd, message, wp=0, lp=0):
            result = real_post(hwnd, message, wp, lp)
            if message == 0x0202:
                time.sleep(0.02)
            return result
        with patch.object(w.U, "GetDoubleClickTime", return_value=1), patch.object(w, "post", side_effect=slow_first_release):
            with self.assertRaisesRegex(w.PilotError, "DOUBLE_CLICK_TIMING_EXPIRED") as failed:
                self.click(frame, action="left_double_click")
        self.observe("double-timing-expired")
        actual = self.state()
        self.assertEqual((actual["releases"], actual["single_downs"], actual["doubles"]), (1, 1, 0))
        self.assertEqual(len(failed.exception.click_evidence["messages"]), 2)
        self.assertTrue(self.service.faulted)
        self.evidence.append({"controlled_failure": "1ms double interval plus delayed first release",
                              "receiver_state": actual, "dispatch_evidence": failed.exception.click_evidence, "no_fallback": True})
