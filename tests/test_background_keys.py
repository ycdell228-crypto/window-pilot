"""Keys are a distinct request, never silently converted to text or foreground input."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import uia, win32 as w, foreground
    from window_pilot.service import Service
    from window_pilot.coordination import Coordinator


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class BackgroundKeyContracts(unittest.TestCase):
    def test_control_keys_have_no_dispatch_route(self):
        # None identities are deliberate: the refusal must not reach any native backend.
        with patch.object(uia, "run_action_worker", side_effect=AssertionError("worker must not launch")), \
             patch.object(w.U, "SendInput", side_effect=AssertionError("real keyboard forbidden")), \
             patch.object(w.U, "PostMessageW", side_effect=AssertionError("keyboard messages forbidden")), \
             patch.object(w.U, "SendMessageTimeoutW", side_effect=AssertionError("text substitution forbidden")), \
             patch.object(foreground, "act", side_effect=AssertionError("foreground fallback forbidden")):
            for keys in (["ENTER"], ["CTRL", "A"], ["ALT", "F4"], ["LEFT"], ["BACKSPACE"]):
                result = uia.act(None, None, None, {"action": "press_key", "keys": keys})
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["effect"], "not_sent")
                self.assertFalse(result["action_attempted"])
                self.assertFalse(result["foreground_fallback"])
                self.assertIsNone(result["execution_method"])

    def test_keys_do_not_accept_text_or_unbounded_sequences(self):
        for args in ({"action": "press_key", "value": "ENTER"},
                     {"action": "press_key", "keys": []},
                     {"action": "press_key", "keys": ["A"] * 5},
                     {"action": "press_key", "keys": ["arbitrary typed text"]},
                     {"action": "press_key", "keys": ["ENTER"], "value": "x"},
                     {"action": "set_value", "keys": ["ENTER"]},
                     {"action": "type_text", "keys": ["ENTER"]}):
            with self.assertRaises(w.PilotError):
                uia.validate_action(args)


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class BackgroundKeyNativeTests(unittest.TestCase):
    def test_real_observation_key_refusal_preserves_value_and_shared_stop(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            services = []
            coordinator = Coordinator(shared=True)
            try:
                for name in ("a", "b"):
                    config = Path(folder) / name / "config.json"
                    config.parent.mkdir()
                    config.write_text('{}')
                    services.append(Service(config, coordinator=coordinator, connection_id=name))
                service, other = services
                hwnd = service.call("launch_test", {})["windows"][0]["hwnd"]
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": hwnd, "access": "observe_and_control",
                    "purpose": "own fixture no background key dispatch"})["target_id"]
                service.call("window_control", {"target_id": token, "operation": "acquire"})
                def observe():
                    tree = service.call("get_window_state", {"target_id": token, "include_screenshot": False})["accessibility"]
                    self.assertEqual(tree["status"], "ok", tree)
                    edit = next(n for n in tree["nodes"] if n["control_type"] == "ControlType.Edit")
                    return tree, edit
                tree, edit = observe()
                self.assertEqual(edit["background_actions"]["press_key"]["supported_keys"], [])
                args = {"target_id": token, "observation_id": tree["observation_id"],
                    "control_id": edit["control_id"], "action": "press_key", "keys": ["CTRL", "A"]}
                with patch.object(uia, "run_action_worker", side_effect=AssertionError("unexpected input worker")):
                    result = service.call("control_action", args)
                self.assertEqual(result["status"], "rejected", result)
                self.assertEqual(result["error"], "BACKGROUND_KEY_BACKEND_UNAVAILABLE")
                self.assertFalse(service.faulted)
                self.assertNotIn(token, service.control_observations)
                with self.assertRaisesRegex(w.PilotError, "STALE_OBSERVATION"):
                    service.call("control_action", args)
                fresh, after = observe()
                self.assertEqual(after["text"]["value"], edit["text"]["value"])
                self.assertEqual(after["text"]["selected_text"], edit["text"]["selected_text"])
                args.update(observation_id=fresh["observation_id"], control_id=after["control_id"])
                other.call("input_control", {"operation": "stop"})
                with self.assertRaisesRegex(w.PilotError, "EXECUTOR_STOPPED"):
                    service.call("control_action", args)
                audit = [json.loads(line) for line in (service.local / "audit.jsonl").read_text(encoding="utf8").splitlines()]
                actions = [row for row in audit if row["event"] == "control_action" and row.get("success")]
                self.assertEqual(actions[-1]["arguments"]["key_count"], 2)
                self.assertNotIn("keys", actions[-1]["arguments"])
                self.assertNotIn('"CTRL"', json.dumps(audit))
                self.assertNotEqual(int(w.U.GetForegroundWindow() or 0), hwnd)
            finally:
                for service in services:
                    service.dispose()
