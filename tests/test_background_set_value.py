"""Reject the Win32 ValuePattern path that failed background acceptance."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class SetValueNativeTests(unittest.TestCase):
    def test_win32_set_value_refused_before_dispatch_and_value_unchanged(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{}')
            service = Service(config)
            evidence = []
            try:
                hwnd = service.call("launch_test", {})["windows"][0]["hwnd"]
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": hwnd, "access": "observe_and_control",
                    "purpose": "own Edit whole-value replacement acceptance"})["target_id"]
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
                    message(0xD, 256, w.C.addressof(buffer))
                    return buffer.value
                def act(tree, edit, text):
                    result = service.call("control_action", {"target_id": token,
                        "observation_id": tree["observation_id"], "control_id": edit["control_id"],
                        "action": "set_value", "value": text})
                    evidence.append({"result": result, "native_value": value()})
                    return result
                self.assertEqual(edit["background_actions"]["set_value"]["reason"], "UIA_VALUE_READ_ONLY")
                result = act(tree, edit, "must-not-write")
                self.assertFalse(result["action_attempted"], result)
                self.assertEqual(value(), "Fixture read-only sample")
                message(0xCF, 0)  # Test-owned Edit becomes writable.
                message(0xB1, 0, 7)  # Select only 'Fixture': set_value must still replace everything.
                for replacement in ("整值 replacement", ""):
                    tree, edit = observe()
                    self.assertEqual(edit["background_actions"]["set_value"]["reason"], "UIA_BACKGROUND_WIN32_SET_VALUE_REFUSED")
                    # Worker must enforce its policy even without advisory cached capabilities.
                    for node in service.control_observations[token]["nodes"]:
                        node["background_actions"] = {}
                    result = act(tree, edit, replacement)
                    self.assertEqual(result["status"], "rejected", result)
                    self.assertEqual(result["error"], "UIA_BACKGROUND_WIN32_SET_VALUE_REFUSED")
                    self.assertFalse(result["action_attempted"], result)
                    self.assertEqual(result["effect"], "not_sent")
                    self.assertEqual(result["execution_method"], "UIA.ValuePattern")
                    self.assertEqual(value(), "Fixture read-only sample")
                    diagnostic = result["desktop_observation"]
                    self.assertFalse(diagnostic["target_was_foreground"], result)
                    self.assertFalse(diagnostic["target_is_foreground_after"], result)
                    self.assertFalse(diagnostic["cursor_changed"], result)
                    with self.assertRaisesRegex(w.PilotError, "STALE_OBSERVATION"):
                        act(tree, edit, "no replay")
                self.assertFalse(service.faulted)
                self.assertNotIn("整值 replacement", (service.local / "audit.jsonl").read_text(encoding="utf8"))
            finally:
                output = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
                if output:
                    path = Path(output)
                    path.mkdir(parents=True, exist_ok=True)
                    (path / "set-value-effects.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf8")
                service.dispose()
