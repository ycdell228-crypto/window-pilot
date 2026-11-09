"""Real worker rejection on own WPF fixture, without provider input."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class BackgroundCapabilitiesNativeTests(unittest.TestCase):
    def test_advertised_value_pattern_does_not_bypass_background_refusal(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{}')
            service = Service(config)
            try:
                hwnd = service.call("launch_test", {"kind": "uia"})["windows"][0]["hwnd"]
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": hwnd, "access": "observe_and_control",
                    "purpose": "own fixture background refusal regression"})["target_id"]
                service.call("window_control", {"target_id": token, "operation": "acquire"})
                def read():
                    tree = service.call("get_window_state", {"target_id": token, "include_screenshot": False})["accessibility"]
                    self.assertEqual(tree["status"], "ok", tree)
                    node = next(n for n in tree["nodes"] if n["automation_id"] == "value-field")
                    return tree, node
                tree, node = read()
                self.assertEqual(node["framework_id"], "WPF")
                self.assertIn("ValuePatternIdentifiers.Pattern", node["supported_patterns"])
                support = node["background_actions"]["set_value"]
                self.assertEqual(support["status"], "refused")
                self.assertEqual(support["reason"], "UIA_BACKGROUND_WPF_SET_VALUE_REFUSED")
                self.assertFalse(support["background_safety_verified"])
                button = next(n for n in tree["nodes"] if n["automation_id"] == "invoke-button")
                self.assertEqual(button["background_actions"]["invoke"]["status"], "unverified")
                disabled = next(n for n in tree["nodes"] if n["automation_id"] == "disabled-button")
                self.assertEqual(disabled["background_actions"]["invoke"]["reason"], "UIA_CONTROL_DISABLED")
                old_value = node["text"]["value"]
                self.assertEqual(old_value["status"], "ok")
                # Snapshot metadata is advisory: the real worker must recompute policy.
                cached = service.control_observations[token]
                for item in cached["nodes"]:
                    item["background_actions"] = {}
                stop_sampling = threading.Event()
                target_front = threading.Event()
                def sample():
                    while not stop_sampling.is_set():
                        if int(w.U.GetForegroundWindow() or 0) == hwnd:
                            target_front.set()
                        stop_sampling.wait(0.01)
                sampler = threading.Thread(target=sample, daemon=True)
                sampler.start()
                try:
                    result = service.call("control_action", {"target_id": token, "observation_id": tree["observation_id"],
                        "control_id": node["control_id"], "action": "set_value", "value": "must not be entered"})
                finally:
                    stop_sampling.set()
                    sampler.join()
                self.assertEqual(result["status"], "rejected", result)
                self.assertEqual(result["error"], support["reason"])
                self.assertEqual(result["execution_method"], "UIA.ValuePattern")
                self.assertEqual(result["effect"], "not_sent")
                self.assertFalse(result["action_attempted"])
                self.assertFalse(service.faulted)
                self.assertNotIn(token, service.control_observations)
                _, after_node = read()
                self.assertEqual(after_node["text"]["value"], old_value)
                after = w.desktop_state()
                # Other foreground windows may change while the human continues working.
                # Sampling is bounded evidence, not proof against sub-sample transitions.
                self.assertFalse(target_front.is_set(), result)
                self.assertNotEqual(after["foreground"], hwnd)
                self.assertNotIn("must not be entered", (service.local / "audit.jsonl").read_text(encoding="utf8"))
            finally:
                service.dispose()
