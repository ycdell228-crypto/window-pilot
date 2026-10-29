"""Read-only native UIA acceptance: project fixture only, no user-app reads or actions."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import uia, win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows imports")
class UiaSourceGuardTests(unittest.TestCase):
    def test_worker_change_invalidates_executor_source_digest(self):
        from window_pilot import admin_service
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module = root / "src/window_pilot/admin_service.py"
            module.parent.mkdir(parents=True)
            module.write_text("# fixture module")
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "runtime_entry.py").write_text("# fixture entry")
            worker = scripts / "uia-observe.ps1"
            worker.write_text("# fixture worker v1")
            manifest = root / "service.json"
            manifest.write_text("{}")
            with patch.object(admin_service, "__file__", str(module)):
                before = admin_service.source_digest(manifest)
                worker.write_text("# fixture worker v2")
                self.assertNotEqual(before, admin_service.source_digest(manifest))


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class UiaNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            raise unittest.SkipTest("requires an interactive local desktop")
        cls.temp = tempfile.TemporaryDirectory()
        config = Path(cls.temp.name) / "config.json"
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        cls.service = Service(config)
        try:
            fixture = cls.service.call("launch_test", {})
            cls.hwnd = fixture["windows"][0]["hwnd"]
            cls.service.call("list_windows", {})
            cls.token = cls.service.call("bind_window", {"hwnd": cls.hwnd})["target_id"]
        except Exception:
            cls.service.dispose()
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.service.call("close_test", {})
        cls.service.dispose()
        cls.temp.cleanup()

    def test_read_tree_without_focus_input_or_values(self):
        before = w.desktop_state()
        title = w.text(self.hwnd)
        result = self.service.call("observe_controls", {"target_id": self.token})
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["values_read"])
        self.assertFalse(result["atomic_snapshot"])
        nodes = {node["name"]: node for node in result["nodes"]}
        button = nodes["UIA sample button"]
        self.assertEqual(button["control_type"], "ControlType.Button")
        self.assertIn("InvokePatternIdentifiers.Pattern", button["supported_patterns"])
        self.assertFalse(nodes["UIA disabled button"]["state"]["enabled"])
        self.assertIn("ControlType.Edit", {node["control_type"] for node in result["nodes"]})
        self.assertIsNotNone(button["parent_control_id"])
        self.assertTrue(all(node["control_id"].startswith(result["observation_id"] + ":") for node in result["nodes"]))
        self.assertTrue(all(node["process_id"] == result["identity"]["pid"] for node in result["nodes"]))
        self.assertAlmostEqual(button["bounds_client"]["x"], 16, delta=2)
        self.assertEqual(w.text(self.hwnd), title)
        after = w.desktop_state()
        self.assertNotEqual(after["foreground"], self.hwnd)
        evidence = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if evidence:
            destination = Path(evidence).resolve()
            self.assertTrue(destination.is_relative_to(Path(__file__).resolve().parents[1] / ".local"))
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "uia-tree.json").write_text(json.dumps({"result": result, "desktop_before": before,
                                                                  "desktop_after": after, "fixture_title_unchanged": True},
                                                                 ensure_ascii=False, indent=2), encoding="utf8")

    def test_limits_and_observation_ids(self):
        first = self.service.call("observe_controls", {"target_id": self.token, "max_nodes": 1})
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(len(first["nodes"]), 1)
        self.assertTrue(first["truncated"])
        second = self.service.call("observe_controls", {"target_id": self.token, "max_depth": 0})
        self.assertEqual(len(second["nodes"]), 1)
        self.assertTrue(second["truncated"])
        self.assertNotEqual(first["observation_id"], second["observation_id"])
        self.assertEqual(self.service.control_observations[self.token]["observation_id"], second["observation_id"])
        with self.assertRaisesRegex(w.PilotError, "UIA_INVALID_LIMITS"):
            self.service.call("observe_controls", {"target_id": self.token, "max_nodes": 129})
        self.assertNotIn(self.token, self.service.control_observations)
        self.assertFalse(self.service.faulted)

    def test_worker_deadline_and_stale_identity(self):
        target = self.service.target(self.token)
        with self.assertRaisesRegex(w.PilotError, "STALE_WINDOW"):
            uia.observe(replace(target, created=target.created + 1))
        # Real child process deadline, not a mocked subprocess or a hung user application.
        result = uia.observe(target, timeout=0.001)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["nodes"], [])
        self.assertIn("no retry", result["error"])
