"""Controlled Win32 failure injection. These are not real UIPI/desktop tests."""
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class ClickFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = Path(self.temp.name) / "config.local.json"
        config.write_text(json.dumps({"window_control": {"capture_backend": "printwindow"}}))
        self.service = Service(config)
        self.target = w.Identity(10001, 123, 456, "test.exe", 789, "TestClass")
        self.child = replace(self.target, hwnd=10002, tid=790, klass="TestChild")
        self.identities = {self.target.hwnd: self.target, self.child.hwnd: self.child}
        self.before_dispatch = self.after_down = self.after_barrier = None
        self.service.targets["target"] = self.target
        self.service.bindings["target"] = {"access": "observe_and_click", "purpose": "fixture", "capture_backend": "printwindow", "input_faulted": False, "awaiting_observation": False, "last_click": None}
        self.args = {"target_id": "target", "frame_id": "frame", "x": 10, "y": 20}
        self.service.frames["frame"] = {"target_id": "target", "size": (200, 100), "time": time.monotonic()}
        self.stack = ExitStack()
        # A valid bound root and its own child; no fake HWND is queried on the desktop.
        self.stack.enter_context(patch.object(w, "identity", side_effect=self.identity))
        self.geometry = self.stack.enter_context(patch.object(w, "geometry", return_value=(200, 100)))
        self.stack.enter_context(patch.object(w, "bindable", side_effect=lambda target: w.verify(target)))
        self.stack.enter_context(patch.object(w, "input_access", return_value={"blocked_by_integrity": False}))
        self.stack.enter_context(patch.object(w, "desktop_state", side_effect=[
            {"foreground": 2, "cursor": [0, 0]}, {"foreground": 3, "cursor": [100, 200]}]))
        self.stack.enter_context(patch.object(w.U, "ClientToScreen", return_value=1))
        self.stack.enter_context(patch.object(w.U, "ScreenToClient", return_value=1))
        self.stack.enter_context(patch.object(w.U, "IsWindowVisible", return_value=1))
        self.stack.enter_context(patch.object(w.U, "IsWindowEnabled", return_value=1))
        self.stack.enter_context(patch.object(w.U, "IsIconic", return_value=0))
        self.stack.enter_context(patch.object(w, "window_style", side_effect=self.window_style))
        self.stack.enter_context(patch.object(w.U, "ChildWindowFromPointEx", side_effect=
            lambda hwnd, point, flags: self.child.hwnd if hwnd == self.target.hwnd else hwnd))
        self.stack.enter_context(patch.object(w.U, "GetAncestor", side_effect=self.ancestor))
        self.post = self.stack.enter_context(patch.object(w.U, "PostMessageW", return_value=1))
        self.barrier = self.stack.enter_context(patch.object(w.U, "SendMessageTimeoutW", return_value=1))
        self.post.side_effect = self.post_message
        self.barrier.side_effect = self.message_barrier
        original_audit = self.service.audit

        def audit(event, **data):
            original_audit(event, **data)
            if event == "click_dispatch_prepared" and self.before_dispatch:
                self.before_dispatch()

        self.stack.enter_context(patch.object(self.service, "audit", side_effect=audit))
        self.stack.enter_context(patch.object(w.C, "get_last_error", return_value=5))
        self.stack.enter_context(patch.object(w.time, "sleep"))

    def tearDown(self):
        self.stack.close()
        self.service.dispose()
        self.temp.cleanup()

    def call(self):
        return self.service.call("click", self.args)

    def identity(self, hwnd):
        if hwnd not in self.identities:
            raise w.PilotError("INVALID_WINDOW")
        return self.identities[hwnd]

    def ancestor(self, hwnd, kind):
        if kind == 2:  # GA_ROOT
            return self.target.hwnd
        return self.target.hwnd if hwnd == self.child.hwnd else 9000

    def window_style(self, hwnd, index):
        if index == -20:  # GWL_EXSTYLE: no transparent exception in these cases
            return 0
        return 0x40000000 if hwnd == self.child.hwnd else 0x00cf0000

    def post_message(self, hwnd, message, wp, lp):
        if self.post.return_value and message == 0x0201 and self.after_down:
            self.after_down()
        return self.post.return_value

    def message_barrier(self, *args):
        if self.barrier.return_value and self.after_barrier:
            self.after_barrier()
        return self.barrier.return_value

    def remove_target(self):
        del self.identities[self.target.hwnd]

    def replace_child(self):
        self.identities[self.child.hwnd] = replace(self.child, tid=791)

    def assert_failed_before_dispatch(self, pattern):
        with self.assertRaisesRegex(w.PilotError, pattern):
            self.call()
        self.assertEqual(self.post.call_count, 0)
        self.assertEqual(self.barrier.call_count, 0)
        self.assertTrue(self.service.faulted)

    def assert_failed_after_dispatch(self, pattern, calls=2):
        with self.assertRaisesRegex(w.PilotError, pattern):
            self.call()
        self.assertEqual(self.post.call_count, calls)
        self.assertTrue(self.service.faulted)
        self.assertNotIn("frame", self.service.frames)
        # A second request cannot replay this input or reuse its old frame.
        with self.assertRaisesRegex(w.PilotError, "STALE_FRAME"):
            self.call()
        self.assertEqual(self.post.call_count, calls)

    def test_normal_activity_succeeds_without_fault(self):
        result = self.call()
        self.assertEqual(result["dispatch"], "posted")
        self.assertEqual(result["effect"], "unverified")
        self.assertTrue(result["desktop_observation"]["changed"])
        self.assertFalse(self.service.faulted)
        self.assertEqual([call.args[:3] for call in self.post.call_args_list],
                         [(self.child.hwnd, 0x0201, 1), (self.child.hwnd, 0x0202, 0)])
        self.assertEqual(self.barrier.call_count, 1)
        self.assertNotIn("frame", self.service.frames)

    def test_expired_frame_is_rejected(self):
        self.service.frames["frame"]["time"] -= 31
        self.assert_failed_before_dispatch("STALE_FRAME")

    def test_wrong_target_frame_is_rejected(self):
        self.service.frames["frame"]["target_id"] = "other"
        self.assert_failed_before_dispatch("STALE_FRAME")

    def test_out_of_bounds_is_rejected(self):
        self.args["x"] = 200
        self.assert_failed_before_dispatch("INVALID_POINT")

    def test_resized_frame_is_rejected(self):
        with patch.object(w, "geometry", return_value=(201, 100)):
            self.assert_failed_before_dispatch("STALE_FRAME")

    def test_missing_target_is_rejected(self):
        with patch.object(w, "verify", side_effect=w.PilotError("INVALID_WINDOW")):
            self.assert_failed_before_dispatch("INVALID_WINDOW")

    def test_child_identity_change_before_dispatch_is_rejected(self):
        self.before_dispatch = self.replace_child
        self.assert_failed_before_dispatch("STALE_CHILD_ROUTE: before down")

    def test_unverified_child_in_other_process_is_rejected(self):
        self.identities[self.child.hwnd] = replace(self.child, pid=124, created=457, exe="other.exe")
        self.assert_failed_before_dispatch("UNVERIFIED_EMBEDDED_HOST_CHAIN")

    def test_child_outside_bound_root_is_rejected(self):
        def escaped(hwnd, kind):
            return 20001 if hwnd == self.child.hwnd and kind == 2 else self.ancestor(hwnd, kind)

        with patch.object(w.U, "GetAncestor", side_effect=escaped):
            self.assert_failed_before_dispatch("CHILD_ESCAPE")

    def test_uipi_down_failure_has_no_accepted_input(self):
        self.post.return_value = 0
        self.assert_failed_after_dispatch("DISPATCH_FAILED: input_sent=false.*Win32 error 5", calls=1)
        self.assertEqual(self.post.call_args.args[1], 0x0201)
        self.assertEqual(self.barrier.call_count, 0)

    def test_release_failure_reports_partial_input_without_replay(self):
        self.post.side_effect = [1, 0]
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=false.*do not replay")
        self.assertEqual(self.barrier.call_count, 0)

    def test_barrier_failure_preserves_dispatch_status(self):
        self.barrier.return_value = 0
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=true.*message barrier")

    def test_target_disappears_after_dispatch(self):
        self.after_barrier = self.remove_target
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=true.*INVALID_WINDOW")
        self.assertEqual(self.barrier.call_count, 1)

    def test_child_replaced_after_dispatch(self):
        self.after_barrier = self.replace_child
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=true.*STALE_CHILD_ROUTE: after dispatch")
        self.assertEqual(self.barrier.call_count, 1)

    def test_target_disappears_between_down_and_up(self):
        self.after_down = self.remove_target
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=false.*INVALID_WINDOW", calls=1)
        self.assertEqual(self.barrier.call_count, 0)

    def test_child_replaced_between_down_and_up(self):
        self.after_down = self.replace_child
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=false.*STALE_CHILD_ROUTE: before release", calls=1)
        self.assertEqual(self.barrier.call_count, 0)

    def test_resize_after_dispatch_reports_input_sent(self):
        self.after_barrier = lambda: setattr(self.geometry, "return_value", (201, 100))
        self.assert_failed_after_dispatch("POST_DISPATCH_ERROR: input_sent=true.*up_posted=true.*resized.*after dispatch")
        self.assertEqual(self.barrier.call_count, 1)


if __name__ == "__main__":
    unittest.main()
