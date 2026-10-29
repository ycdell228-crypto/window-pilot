"""Real UIA pattern effects on the project-owned WPF fixture; never user software."""
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
class UiaActionNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            raise unittest.SkipTest("requires interactive local desktop")
        cls.temp = tempfile.TemporaryDirectory()
        config = Path(cls.temp.name) / "config.json"
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        cls.service = Service(config)
        try:
            launched = cls.service.call("launch_test", {"kind": "uia"})
            cls.hwnd = launched["windows"][0]["hwnd"]
            cls.service.call("list_windows", {})
            cls.token = cls.service.call("bind_window", {"hwnd": cls.hwnd, "access": "observe_and_control",
                                                        "purpose": "project-owned five-pattern acceptance"})["target_id"]
            cls.evidence = []
        except Exception:
            cls.service.dispose(); cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.service.call("close_test", {})
        cls.service.dispose()
        destination = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if destination:
            path = Path(destination).resolve()
            if not path.is_relative_to(Path(__file__).resolve().parents[1] / ".local"):
                raise AssertionError("evidence must stay private in this checkout")
            path.mkdir(parents=True, exist_ok=True)
            (path / "uia-action-effects.json").write_text(json.dumps(cls.evidence, ensure_ascii=False, indent=2), encoding="utf8")
        cls.temp.cleanup()

    def observe(self, token=None):
        tree = self.service.call("observe_controls", {"target_id": token or self.token, "max_nodes": 128, "max_depth": 8})
        self.assertEqual(tree["status"], "ok", tree)
        self.assertFalse(tree["truncated"], "fixture should fit within the public bounds")
        return tree

    def node(self, tree, identifier):
        nodes = [node for node in tree["nodes"] if node["automation_id"] == identifier]
        self.assertEqual(len(nodes), 1, (identifier, tree))
        return nodes[0]

    def act(self, tree, identifier, action, token=None, **parameters):
        node = self.node(tree, identifier)
        return self.service.call("control_action", {"target_id": token or self.token, "observation_id": tree["observation_id"],
                                                    "control_id": node["control_id"], "action": action, **parameters})

    def test_five_pattern_effects_and_single_use(self):
        before = self.observe()
        result = self.act(before, "invoke-button", "invoke")
        self.assertEqual(result["status"], "provider_returned", result)
        self.assertEqual(result["effect"], "unverified")
        with self.assertRaisesRegex(w.PilotError, "UIA_STALE_OBSERVATION"):
            self.act(before, "invoke-button", "invoke")
        with self.assertRaisesRegex(w.PilotError, "UIA_STALE_OBSERVATION"):
            self.act(before, "Option-B", "select")
        after = self.observe()
        self.assertEqual(self.node(after, "invoke-status")["name"], "Invoked: 1")
        self.evidence.append({"action": "invoke", "verified": "Invoked: 1", "diagnostic": result["desktop_observation"]})
        sample = "fixture acceptance value 42"
        result = self.act(after, "value-field", "set_value", value=sample)
        self.assertEqual(result["status"], "provider_returned", result)
        after = self.observe()
        self.assertEqual(self.node(after, "value-status")["name"], "Value echo: " + sample)
        self.evidence.append({"action": "set_value", "verified": "fixture echo matches exact synthetic input", "diagnostic": result["desktop_observation"]})
        self.assertNotIn(sample, (self.service.local / "audit.jsonl").read_text(encoding="utf8"))
        result = self.act(after, "Option-B", "select")
        self.assertEqual(result["status"], "provider_returned", result)
        after = self.observe()
        self.assertTrue(self.node(after, "Option-B")["pattern_state"]["selected"])
        self.assertFalse(self.node(after, "Option-A")["pattern_state"]["selected"])
        self.evidence.append({"action": "select", "verified": "Option B selected, Option A deselected", "diagnostic": result["desktop_observation"]})
        for action, expected in (("expand", "Expanded"), ("collapse", "Collapsed")):
            result = self.act(after, "expander", action)
            self.assertEqual(result["status"], "provider_returned", result)
            after = self.observe()
            self.assertEqual(self.node(after, "expander")["pattern_state"]["expand_collapse"], expected)
            self.evidence.append({"action": action, "verified": expected, "diagnostic": result["desktop_observation"]})
        prior_percent = self.node(after, "scroll-view")["pattern_state"]["vertical_scroll_percent"]
        result = self.act(after, "scroll-view", "scroll", vertical="LargeIncrement")
        self.assertEqual(result["status"], "provider_returned", result)
        after = self.observe()
        current_percent = self.node(after, "scroll-view")["pattern_state"]["vertical_scroll_percent"]
        self.assertGreater(current_percent, prior_percent)
        self.evidence.append({"action": "scroll", "before": prior_percent, "after": current_percent, "diagnostic": result["desktop_observation"]})

    def test_reject_read_only_disabled_password_unsupported_expired_and_geometry(self):
        self.service.call("list_windows", {})
        read_only = self.service.call("bind_window", {"hwnd": self.hwnd})["target_id"]
        try:
            tree = self.observe(read_only)
            with self.assertRaisesRegex(w.PilotError, "UIA_CONTROL_ACCESS_REQUIRED"):
                self.act(tree, "invoke-button", "invoke", token=read_only)
        finally:
            self.service.call("unbind_window", {"target_id": read_only})
        for identifier, action, code, parameters in (
            ("disabled-button", "invoke", "UIA_CONTROL_DISABLED", {}),
            ("value-status", "invoke", "UIA_PATTERN_UNSUPPORTED", {}),
            ("password-field", "set_value", "UIA_PASSWORD_CONTROL_REFUSED", {"value": "not-sent"}),
        ):
            tree = self.observe()
            result = self.act(tree, identifier, action, **parameters)
            self.assertEqual(result["status"], "rejected", result)
            self.assertFalse(result["action_attempted"])
            self.assertEqual(result["error"], code)
            self.assertNotIn(self.token, self.service.control_observations)
            self.evidence.append({"rejected": code, "action_attempted": False})
        tree = self.observe()
        self.service.control_observations[self.token]["time"] -= 31  # controlled age injection, not waiting/replay
        with self.assertRaisesRegex(w.PilotError, "UIA_STALE_OBSERVATION"):
            self.act(tree, "invoke-button", "invoke")
        tree = self.observe()
        w.api(w.U, "GetWindowRect", w.W.BOOL, w.W.HWND, w.C.POINTER(w.W.RECT))
        w.api(w.U, "SetWindowPos", w.W.BOOL, w.W.HWND, w.W.HWND, w.C.c_int, w.C.c_int, w.C.c_int, w.C.c_int, w.W.UINT)
        rect = w.W.RECT()
        w.check(w.U.GetWindowRect(self.hwnd, w.C.byref(rect)), "fixture rectangle")
        try:
            w.check(w.U.SetWindowPos(self.hwnd, None, rect.left + 8, rect.top + 8, 0, 0, 0x15), "move fixture without activation")
            with self.assertRaisesRegex(w.PilotError, "UIA_WINDOW_GEOMETRY_CHANGED"):
                self.act(tree, "invoke-button", "invoke")
        finally:
            w.U.SetWindowPos(self.hwnd, None, rect.left, rect.top, 0, 0, 0x15)
        self.assertFalse(self.service.faulted)

    def test_z_unknown_worker_outcome_stops_input_without_replay(self):
        from window_pilot import uia
        tree = self.observe()
        real_act = uia.act
        with patch.object(uia, "act", side_effect=lambda target, observation, node, args: real_act(target, observation, node, args, timeout=0.001)):
            result = self.act(tree, "invoke-button", "invoke")
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(self.service.faulted)
        self.assertNotIn(self.token, self.service.control_observations)
        updated = self.observe()  # read remains available; it cannot reset the input fault
        with self.assertRaisesRegex(w.PilotError, "BINDING_INPUT_FAULTED"):
            self.act(updated, "invoke-button", "invoke")
        self.evidence.append({"unknown_outcome": "real worker killed at 1ms", "binding_input_faulted": True, "replay_refused": True})

    def test_y_post_dispatch_diagnostic_failure_preserves_unknown_and_stops_input(self):
        # A separate fixture/connection: the real provider runs, then one local diagnostic fails.
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text("{}")
            service = Service(config)
            try:
                launched = service.call("launch_test", {"kind": "uia"})
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": launched["windows"][0]["hwnd"], "access": "observe_and_control",
                                                       "purpose": "fixture post-dispatch unknown outcome"})["target_id"]
                tree = service.call("observe_controls", {"target_id": token})
                button = self.node(tree, "invoke-button")
                real_before = w.desktop_state()
                with patch.object(w, "desktop_state", side_effect=[real_before, w.PilotError("controlled diagnostic unavailable")]):
                    result = service.call("control_action", {"target_id": token, "observation_id": tree["observation_id"],
                                                              "control_id": button["control_id"], "action": "invoke"})
                self.assertEqual(result["status"], "unknown", result)
                self.assertTrue(result["action_attempted"])
                self.assertTrue(service.faulted)
                after = service.call("observe_controls", {"target_id": token})
                self.assertEqual(self.node(after, "invoke-status")["name"], "Invoked: 1")
                self.evidence.append({"unknown_outcome": "real Invoke returned, controlled post-action desktop failure",
                                      "actual_effect": "Invoked: 1", "binding_input_faulted": True})
                service.call("close_test", {})
            finally:
                service.dispose()


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class UiaChangedTreeNativeTests(unittest.TestCase):
    def test_changed_name_in_same_window_rejects_old_snapshot(self):
        if not w.U.GetForegroundWindow() or os.environ.get("CI"):
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text("{}")
            service = Service(config)
            try:
                launched = service.call("launch_test", {})
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": launched["windows"][0]["hwnd"], "access": "observe_and_control",
                                                       "purpose": "fixture stale tree rejection"})["target_id"]
                tree = service.call("observe_controls", {"target_id": token})
                self.assertEqual(tree["status"], "ok", tree)
                button = next(node for node in tree["nodes"] if node["name"] == "UIA sample button")
                w.api(w.U, "SetWindowTextW", w.W.BOOL, w.W.HWND, w.W.LPCWSTR)
                w.check(w.U.SetWindowTextW(button["native_window_handle"], "Fixture changed label"), "change own fixture label")
                result = service.call("control_action", {"target_id": token, "observation_id": tree["observation_id"],
                                                          "control_id": button["control_id"], "action": "invoke"})
                self.assertEqual(result["status"], "rejected", result)
                self.assertEqual(result["error"], "UIA_OBSERVATION_CHANGED")
                self.assertFalse(result["action_attempted"])
                service.call("close_test", {})
            finally:
                service.dispose()
