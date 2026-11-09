"""Actual native Edit insertion, selection replacement and stale-caret refusal."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

if sys.platform == "win32":
    from window_pilot import win32 as w, uia
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class TypeTextContracts(unittest.TestCase):
    def test_text_and_control_keys_are_distinct(self):
        uia.validate_action({"action": "type_text", "value": "insert"})
        for args in ({"action": "type_text"}, {"action": "type_text", "value": "x\0y"},
                     {"action": "type_text", "value": "x", "keys": ["ENTER"]},
                     {"action": "press_key", "value": "ENTER"}):
            with self.assertRaises(w.PilotError):
                uia.validate_action(args)


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class TypeTextNativeTests(unittest.TestCase):
    def test_insert_replace_selection_and_reject_changed_caret(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{}')
            service = Service(config)
            try:
                hwnd = service.call("launch_test", {})["windows"][0]["hwnd"]
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": hwnd, "access": "observe_and_control",
                    "purpose": "own native Edit insertion acceptance"})["target_id"]
                def observe():
                    tree = service.call("get_window_state", {"target_id": token, "include_screenshot": False})["accessibility"]
                    self.assertEqual(tree["status"], "ok", tree)
                    return tree, next(n for n in tree["nodes"] if n["control_type"] == "ControlType.Edit")
                tree, edit = observe()
                child = edit["native_window_handle"]
                def message(code, wp=0, lp=0):
                    result = w.C.c_size_t()
                    self.assertTrue(w.U.SendMessageTimeoutW(child, code, wp, lp, 0x23, 1000, w.C.byref(result)))
                def value():
                    buffer = w.C.create_unicode_buffer(256)
                    message(0xD, 256, w.C.addressof(buffer))  # Independent WM_GETTEXT oracle, not UIA readback.
                    return buffer.value
                def act(tree, edit, text):
                    return service.call("control_action", {"target_id": token, "observation_id": tree["observation_id"],
                        "control_id": edit["control_id"], "action": "type_text", "value": text})
                self.assertEqual(edit["background_actions"]["type_text"]["status"], "refused")
                rejected = act(tree, edit, "not-written")
                self.assertEqual(rejected["status"], "rejected", rejected)
                self.assertEqual(value(), "Fixture read-only sample")
                message(0xCF, 0)  # EM_SETREADONLY(false), test-owned child only.
                message(0xB1, 0, 7)  # Select exactly 'Fixture', without focus.
                tree, edit = observe()
                self.assertEqual(edit["native_edit"]["start"], 0)
                self.assertEqual(edit["native_edit"]["end"], 7)
                result = act(tree, edit, "后台")
                self.assertEqual(result["status"], "provider_returned", result)
                self.assertEqual(result["execution_method"], "Win32.EM_REPLACESEL")
                self.assertEqual(value(), "后台 read-only sample")
                with self.assertRaisesRegex(w.PilotError, "STALE_OBSERVATION"):
                    act(tree, edit, "no replay")
                tree, edit = observe()
                # The native caret is now after the inserted text; preserve both surrounding sides.
                result = act(tree, edit, "插入")
                self.assertEqual(result["status"], "provider_returned", result)
                self.assertEqual(value(), "后台插入 read-only sample")
                tree, edit = observe()
                message(0xB1, 0, 0)
                result = act(tree, edit, "must-not-enter")
                self.assertEqual(result["status"], "rejected", result)
                self.assertFalse(result["action_attempted"])
                self.assertEqual(value(), "后台插入 read-only sample")
                self.assertFalse(service.faulted)
                tree, edit = observe()
                result = act(tree, edit, "line1\nline2")
                self.assertEqual(result["error"], "UIA_EDIT_MULTILINE_REQUIRED", result)
                self.assertEqual(value(), "后台插入 read-only sample")
                self.assertNotEqual(int(w.U.GetForegroundWindow() or 0), hwnd)
                self.assertNotIn("must-not-enter", (service.local / "audit.jsonl").read_text(encoding="utf8"))
            finally:
                service.dispose()
