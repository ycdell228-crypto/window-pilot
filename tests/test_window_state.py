"""Unified read-only observation contracts and actual WPF text effects."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class WindowStateContracts(unittest.TestCase):
    def test_empty_selection_rejects_without_window_access(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{}')
            service = Service(config)
            try:
                with self.assertRaisesRegex(w.PilotError, "WINDOW_STATE_EMPTY_REQUEST"):
                    service.call("get_window_state", {"target_id": "invalid", "include_screenshot": False,
                                                      "include_accessibility": False})
            finally:
                service.dispose()


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class WindowStateNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            raise unittest.SkipTest("requires interactive local desktop")
        cls.temp = tempfile.TemporaryDirectory()
        config = Path(cls.temp.name) / "config.json"
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        cls.service = Service(config)
        try:
            result = cls.service.call("launch_test", {"kind": "uia"})
            cls.hwnd = result["windows"][0]["hwnd"]
            cls.service.call("list_windows", {})
            cls.token = cls.service.call("bind_window", {"hwnd": cls.hwnd})["target_id"]
        except Exception:
            cls.service.dispose()
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.service.dispose()
        cls.temp.cleanup()

    def state(self, **kwargs):
        return self.service.call("get_window_state", {"target_id": self.token, **kwargs})

    def test_real_values_selection_password_and_image(self):
        before = w.desktop_state()
        result = self.state()
        self.assertEqual(result["status"], "ok", result.get("accessibility"))
        self.assertFalse(result["atomic_snapshot"])
        self.assertTrue(result["image"])
        controls = result["accessibility"]
        self.assertEqual(controls["frame_id"], result["screenshot"]["frame_id"])
        nodes = {n["automation_id"]: n for n in controls["nodes"]}
        field = nodes["value-field"]["text"]
        self.assertEqual(field["value"]["text"], "initial")
        self.assertEqual(field["document_text"]["text"].rstrip(), "initial")
        # WPF selection is deliberately unsupported: never focus or return invented text.
        self.assertEqual(field["selected_text"], {"status": "unsupported",
                         "reason": "background_selection_provider_not_validated"})
        self.assertEqual(nodes["invoke-button"]["text"]["value"]["status"], "unsupported")
        for value in nodes["password-field"]["text"].values():
            self.assertEqual(value, {"status": "password_filtered"})
        self.assertNotIn("fixture-private-value", json.dumps(controls))
        self.assertIn(nodes["Option-A"]["control_id"], controls["selected_control_ids"])
        after = w.desktop_state()
        self.assertNotEqual(before["foreground"], self.hwnd)
        self.assertNotEqual(after["foreground"], self.hwnd)
        evidence = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if evidence:
            import base64
            folder = Path(evidence).resolve()
            self.assertTrue(folder.is_relative_to(Path(__file__).resolve().parents[1] / ".local"))
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "window.png").write_bytes(base64.b64decode(result.pop("image")))
            (folder / "state.json").write_text(json.dumps({"result": result, "before": before, "after": after}, ensure_ascii=False, indent=2), encoding="utf8")

    def test_text_budget_and_opt_out_keep_old_interface(self):
        result = self.state(include_screenshot=False, max_text_length=3, max_total_text_length=5)
        self.assertIsNone(result["screenshot"])
        self.assertNotIn("image", result)
        texts = [t for n in result["accessibility"]["nodes"] for t in n["text"].values()]
        self.assertLessEqual(sum(len(t.get("text", "").encode("utf-16-le")) // 2 for t in texts), 5)
        value = next(n for n in result["accessibility"]["nodes"] if n["automation_id"] == "value-field")["text"]["value"]
        self.assertEqual(value, {"status": "truncated", "text": "ini", "truncated": True})
        plain = self.state(include_screenshot=False, include_text=False)
        self.assertFalse(plain["accessibility"]["values_read"])
        self.assertTrue(all("text" not in n for n in plain["accessibility"]["nodes"]))
        old = self.service.call("observe_controls", {"target_id": self.token})
        self.assertFalse(old["values_read"])

    def test_failed_capture_does_not_return_old_credentials_or_fallback(self):
        self.state(include_screenshot=False)
        with patch.object(w, "capture", side_effect=w.PilotError("CAPTURE_TEST_FAILURE")):
            with self.assertRaisesRegex(w.PilotError, "CAPTURE_TEST_FAILURE"):
                self.state()
        self.assertNotIn(self.token, self.service.control_observations)

    def test_uia_timeout_is_partial_without_control_credential(self):
        from window_pilot import uia
        actual = uia.observe
        def timeout(*args, **kwargs):
            return actual(*args, **kwargs, timeout=0.001)
        with patch.object(uia, "observe", side_effect=timeout):
            result = self.state()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["accessibility"]["status"], "timeout")
        self.assertTrue(result["image"])
        self.assertNotIn(self.token, self.service.control_observations)

    def test_faulted_window_remains_readable_without_clearing_fault(self):
        self.service.bindings[self.token]["input_faulted"] = True
        try:
            result = self.state()
            self.assertTrue(result["screenshot"]["binding_input_faulted"])
            self.assertTrue(self.service.bindings[self.token]["input_faulted"])
        finally:
            self.service.bindings[self.token]["input_faulted"] = False

    def test_resize_between_screenshot_and_tree_rejects_both_credentials(self):
        get_rect = w.api(w.U, "GetWindowRect", w.W.BOOL, w.W.HWND, w.C.POINTER(w.W.RECT))
        set_pos = w.api(w.U, "SetWindowPos", w.W.BOOL, w.W.HWND, w.W.HWND,
                        w.C.c_int, w.C.c_int, w.C.c_int, w.C.c_int, w.W.UINT)
        rect = w.W.RECT()
        self.assertTrue(get_rect(self.hwnd, w.C.byref(rect)))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        capture = w.capture
        old_frames = set(self.service.frames)

        def capture_then_resize(*args, **kwargs):
            result = capture(*args, **kwargs)
            # Only the test-owned HWND; SWP_NOMOVE|NOZORDER|NOACTIVATE.
            self.assertTrue(set_pos(self.hwnd, None, 0, 0, width + 40, height, 0x16))
            self.assertNotEqual(w.geometry(self.hwnd), result[1])
            return result

        try:
            with patch.object(w, "capture", side_effect=capture_then_resize):
                with self.assertRaisesRegex(w.PilotError, "WINDOW_STATE_GEOMETRY_CHANGED"):
                    self.state()
            self.assertEqual(set(self.service.frames), old_frames)
            self.assertNotIn(self.token, self.service.control_observations)
        finally:
            self.assertTrue(set_pos(self.hwnd, None, 0, 0, width, height, 0x16))


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class NativeEditSelectionTests(unittest.TestCase):
    def test_actual_win32_selection_read_without_focus(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{}')
            service = Service(config)
            try:
                hwnd = service.call("launch_test", {})["windows"][0]["hwnd"]
                self.assertNotEqual(w.desktop_state()["foreground"], hwnd, "fixture launch")
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": hwnd})["target_id"]
                state = service.call("get_window_state", {"target_id": token, "include_screenshot": False})
                self.assertNotEqual(w.desktop_state()["foreground"], hwnd, "first text observation")
                edit = next(n for n in state["accessibility"]["nodes"] if n["control_type"] == "ControlType.Edit")
                # Set selection ONLY in the test-owned child, no keyboard/focus injection.
                result = w.C.c_size_t()
                self.assertTrue(w.U.SendMessageTimeoutW(edit["native_window_handle"], 0x00B1, 0, 7, 2, 1000, w.C.byref(result)))
                self.assertNotEqual(w.desktop_state()["foreground"], hwnd, "fixture selection initialization")
                state = service.call("get_window_state", {"target_id": token, "include_screenshot": False})
                edit = next(n for n in state["accessibility"]["nodes"] if n["control_type"] == "ControlType.Edit")
                self.assertEqual(edit["text"]["value"].get("text"), "Fixture read-only sample")
                self.assertEqual(edit["text"]["selected_text"].get("text"), "Fixture", edit["text"])
                self.assertNotEqual(w.desktop_state()["foreground"], hwnd)
            finally:
                service.dispose()
